"""Resume unscored eval cases with delay/backoff for free-tier rate limits."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evals'))
from run_evals import run_case
from grading import summarize, bonus_points


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='eval_before.json')
    parser.add_argument('--delay', type=float, default=20.0, help='Seconds between cases')
    parser.add_argument('--retries', type=int, default=4)
    parser.add_argument('--provider', default=os.getenv('PROVIDER', 'groq'))
    parser.add_argument('--model', default=os.getenv('MODEL'))
    parser.add_argument('--judge-provider', default=os.getenv('JUDGE_PROVIDER'))
    parser.add_argument('--judge-model', default=os.getenv('JUDGE_MODEL'))
    parser.add_argument('--max-steps', type=int, default=None)
    parser.add_argument('--bonus', action='store_true')
    parser.add_argument('--init', action='store_true', help='Create empty report from cases and exit')
    args = parser.parse_args()
    args.judge_provider = args.judge_provider or args.provider
    args.judge_model = args.judge_model or args.model
    if not args.model:
        parser.error('Thiếu MODEL')
    if args.max_steps is None:
        args.max_steps = 16 if args.bonus else 8

    path = Path(args.output)
    cases_path = Path('bonus/cases.json') if args.bonus else Path('evals/cases.json')
    all_cases = json.loads(cases_path.read_text(encoding='utf-8'))
    case_defs = {c['id']: c for c in all_cases}

    if args.init or not path.exists():
        report = {
            'summary': {'total_cases': len(all_cases), 'scored_cases': 0, 'unscored_cases': len(all_cases),
                        'score_0_100': None, 'partial_mean_0_100': None},
            'config': {
                'provider': args.provider, 'model': args.model,
                'judge_provider': args.judge_provider, 'judge_model': args.judge_model,
                'max_steps': args.max_steps, 'dataset': 'bonus' if args.bonus else 'core',
            },
            'cases': [{
                'id': c['id'], 'question': c['question'], 'expected': c['expected'],
                'scenario': c.get('scenario', 'normal'), 'provider': args.provider, 'model': args.model,
                'judge_provider': args.judge_provider, 'judge_model': args.judge_model,
                'result': {'status': 'error', 'answer': '', 'trace': [], 'usage': [], 'error': 'pending'},
                'grade': {'score': None, 'status': 'unscored', 'reason': 'pending'},
            } for c in all_cases],
        }
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'Khởi tạo {path} với {len(all_cases)} case unscored.', flush=True)
        if args.init:
            return 0

    report = json.loads(path.read_text(encoding='utf-8'))

    pending = [item for item in report['cases'] if item.get('grade', {}).get('status') == 'unscored']
    print(f'Cần chạy lại {len(pending)} case unscored...', flush=True)

    by_id = {item['id']: item for item in report['cases']}
    for item in pending:
        case = case_defs[item['id']]
        ok = False
        for attempt in range(1, args.retries + 1):
            print(f"Đang chạy {case['id']} (lần {attempt}/{args.retries})", flush=True)
            result = run_case(case, args)
            score = result['grade'].get('score')
            status = result['grade'].get('status')
            err = (result['result'].get('error') or result['grade'].get('reason') or '')
            print(f"{case['id']}: {score} ({status})", flush=True)
            if status == 'scored' or (status != 'unscored' and '429' not in err and 'Rate' not in err):
                by_id[case['id']] = result
                ok = True
                break
            wait = args.delay * attempt
            print(f'Rate limit/unscored — chờ {wait:.0f}s...', flush=True)
            time.sleep(wait)
        if not ok:
            by_id[case['id']] = result

        ordered = [by_id[c['id']] for c in json.loads(cases_path.read_text(encoding='utf-8')) if c['id'] in by_id]
        report['cases'] = ordered
        report['summary'] = summarize(ordered)
        report['config'] = {
            'provider': args.provider,
            'model': args.model,
            'judge_provider': args.judge_provider,
            'judge_model': args.judge_model,
            'max_steps': args.max_steps,
            'dataset': 'bonus' if args.bonus else 'core',
        }
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f"Đã lưu tạm: scored {report['summary']['scored_cases']}/{report['summary']['total_cases']}", flush=True)
        time.sleep(args.delay)

    s = report['summary']
    if args.bonus:
        full_run = len(report['cases']) == len(all_cases) and s.get('unscored_cases', 1) == 0
        s['bonus_points_0_15'] = bonus_points(s.get('score_0_100'), full_run)
        report['summary'] = s
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f"Điểm bonus tham khảo: {s['bonus_points_0_15']}/15", flush=True)
    print(f"Điểm: {s['score_0_100']}/100; đã chấm {s['scored_cases']}/{s['total_cases']}. File: {path}", flush=True)
    return 0 if s['score_0_100'] is not None else 1


if __name__ == '__main__':
    raise SystemExit(main())

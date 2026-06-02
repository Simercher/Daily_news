import argparse, json
from news_system.jobs import collect_job, daily_event_job, breaking_watch_job

def main(argv=None):
    p=argparse.ArgumentParser(prog='daily-news'); sub=p.add_subparsers(dest='cmd', required=True)
    c=sub.add_parser('collect'); c.add_argument('--source', default='all'); c.add_argument('--lookback-hours', type=int, default=1)
    sub.add_parser('build-events'); sub.add_parser('watch-breaking'); sub.add_parser('show-daily'); sub.add_parser('show-breaking')
    args=p.parse_args(argv)
    if args.cmd=='collect': print(json.dumps({'articles': len(collect_job(args.source,args.lookback_hours))}))
    elif args.cmd in ('build-events','show-daily'): print(json.dumps({'events': len(daily_event_job([]))}))
    else: print(json.dumps({'breaking': len(breaking_watch_job([]))}))
if __name__=='__main__': main()

#!/usr/bin/env python3
"""Validate two public posts and an idempotent five-cell social reporting row."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from update_manifest import IDENTITIES, SHEET_ID, SHEET_URL, WEBSITE_VALUE, load_manifest, validate_post_url


def expected_row(m):
    urls=[];times=[]
    if m.get('mode') != 'live': raise ValueError('Dry-runs have no live completion row')
    for c,identity in IDENTITIES.items():
        r=m['channels'][c]
        if r.get('status')!='published' or r.get('identity_id')!=identity or not r.get('submission_started_at'):
            raise ValueError(f'{c} has no verified publication to the intended identity')
        urls.append(validate_post_url(c,r.get('url')))
        if not Path(r.get('evidence','')).is_file(): raise ValueError(f'{c} verification evidence is missing')
        t=datetime.fromisoformat(r['verified_at'])
        if t.tzinfo is None: raise ValueError('Verification timestamps need a timezone')
        times.append(t)
    # Stable across Sheet retries; no website timestamp exists for a social-only campaign.
    when=max(times).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
    return ['vantrendtools.com',when,WEBSITE_VALUE,*urls]


def validate_completion(m):
    values=expected_row(m)
    r=m['reporting']['google_sheet']
    if m.get('status')!='published': raise ValueError('Both channels must be published')
    if r.get('status')!='reported' or r.get('spreadsheet_id')!=SHEET_ID or r.get('sheet_name')!='工作表1':
        raise ValueError('Google Sheet row has not been verified at the fixed destination')
    if r.get('domain')!='vantrendtools.com' or r.get('website_value')!=WEBSITE_VALUE:
        raise ValueError('Reporting domain or social-only marker mismatch')
    if r.get('url')!=SHEET_URL or int(r.get('external_id',0))<2 or r.get('values')!=values:
        raise ValueError('Sheet URL, row or verified values mismatch')
    if not Path(r.get('evidence','')).is_file(): raise ValueError('Sheet read-back evidence is missing')
    return {'status':'complete','facebook':values[3],'linkedin':values[4],
            'google_sheet':{'url':SHEET_URL,'row':int(r['external_id']),'status':'reported'},'website':'not_applicable'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest',type=Path)
    p.add_argument('--row-only',action='store_true',help='Print prospective row after both posts are verified')
    a=p.parse_args();m=load_manifest(a.manifest)
    print(json.dumps(expected_row(m) if a.row_only else validate_completion(m),ensure_ascii=False,indent=2))

if __name__=='__main__':
    try: main()
    except (ValueError,KeyError,OSError) as e:
        print(f'error: {e}',file=sys.stderr);sys.exit(1)

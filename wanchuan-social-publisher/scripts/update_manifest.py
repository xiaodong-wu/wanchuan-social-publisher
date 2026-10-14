#!/usr/bin/env python3
"""Atomically record social submissions, verified outcomes, and Sheets reporting."""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

IDENTITIES = {'facebook': '61575467138674', 'linkedin': '146727123'}
SHEET_ID = '18iLpJ7bpDbJzxYtg0vsSOQxOR2e0KBuMI9C7LK0MhAw'
SHEET_URL = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit'
WEBSITE_VALUE = '不适用（仅社媒）'


def load_manifest(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('skill') != 'wanchuan-social-publisher' or set(data.get('channels', {})) != set(IDENTITIES):
        raise ValueError('Expected a Wanchuan two-channel manifest')
    return data


def write_manifest(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix=f'.{path.name}.', delete=False) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
        temp = f.name
    os.replace(temp, path)


def validate_post_url(channel, value):
    p = urlparse(value or '')
    if p.scheme != 'https' or p.hostname != f'www.{channel}.com' or p.username or p.password or p.port:
        raise ValueError(f'{channel} requires a public HTTPS post URL on the exact platform host')
    if channel == 'facebook':
        q = parse_qs(p.query)
        valid = bool(re.search(r'/(?:posts|photos|videos)/[^/]+', p.path)) or (
            p.path in {'/permalink.php', '/story.php', '/photo.php', '/photo/'} and ('story_fbid' in q or 'fbid' in q))
        if 'id' in q and q['id'] != [IDENTITIES[channel]]:
            raise ValueError('Facebook permalink belongs to another page')
    else:
        valid = bool(re.fullmatch(r'/feed/update/urn:li:activity:\d+/?', p.path) or re.match(r'/posts/[^/]+', p.path))
    if not valid:
        raise ValueError('Use a post permalink, not a profile, dashboard, composer or feed URL')
    return value


def calculate_run_status(channels):
    states = [v.get('status') for v in channels.values()]
    if all(s == 'published' for s in states): return 'published'
    if 'published' in states: return 'partial'
    if 'blocked' in states: return 'blocked'
    if 'failed' in states: return 'failed'
    return 'prepared'


def update_manifest(path, channel, status, *, url=None, error=None, external_id=None,
                    submission_started=False, evidence=None, identity_id=None, values_file=None):
    data = load_manifest(path)
    social = channel in IDENTITIES
    if not social and channel != 'google_sheet': raise ValueError('Unknown channel')
    allowed = {'pending', 'published', 'failed', 'blocked'} if social else {'pending', 'reported', 'failed', 'blocked'}
    if status not in allowed: raise ValueError('Invalid status for channel')
    if data['mode'] != 'live' and (submission_started or status in {'published', 'reported'}):
        raise ValueError('A dry-run cannot record live submissions or external success')
    old = data['channels'][channel] if social else data['reporting']['google_sheet']
    if old.get('status') in {'published', 'reported'}:
        raise ValueError('Already successful: preserve this outcome and skip the channel')
    now = datetime.now(timezone.utc).isoformat()
    record = {**old, 'status': status, 'updated_at': now}
    if social and old.get('identity_id') != IDENTITIES[channel]: raise ValueError('Wrong target identity')
    if submission_started:
        if not social or status != 'pending': raise ValueError('Mark submission only as pending on a social channel')
        from validate_campaign import validate_campaign
        validate_campaign(data)
        record.setdefault('submission_started_at', now)
        data.setdefault('publishing_started_at', now)
    if status == 'published':
        if not old.get('submission_started_at'): raise ValueError('Missing permanent submission marker')
        validate_post_url(channel, url)
        if identity_id != IDENTITIES[channel]: raise ValueError('Verified publisher identity does not match')
    if status in {'published', 'reported'}:
        if not evidence or not Path(evidence).is_file() or Path(evidence).stat().st_size == 0:
            raise ValueError('Save public verification or Sheet read-back evidence first')
        record.update(evidence=str(Path(evidence).resolve()), verified_at=now)
        record.pop('error', None)
    if status == 'reported':
        from validate_completion import expected_row
        values = json.loads(Path(values_file).read_text()) if values_file else None
        if values != expected_row(data): raise ValueError('Sheet read-back values must equal the exact five-cell row')
        if url != SHEET_URL or int(external_id or 0) < 2: raise ValueError('Wrong reporting destination or row')
        readback = json.loads(Path(evidence).read_text())
        if readback.get('spreadsheet_id') != SHEET_ID or str(readback.get('row')) != str(external_id) or readback.get('values') != values or readback.get('matching_rows') != 1:
            raise ValueError('Read-back evidence must verify destination, row, exact cells and a unique match')
        record['values'] = values
    if url: record['url'] = url
    if error: record['error'] = str(error)[:2000]
    if external_id is not None: record['external_id'] = external_id
    if social: data['channels'][channel] = record
    else: data['reporting']['google_sheet'] = record
    data.setdefault('history', []).append({'channel': channel, **record})
    data['status'] = calculate_run_status(data['channels'])
    data['updated_at'] = now
    write_manifest(path, data)
    return data


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest',type=Path)
    p.add_argument('--channel',choices=[*IDENTITIES,'google_sheet'],required=True)
    p.add_argument('--status',required=True)
    for key in ['url','error','external-id','evidence','identity-id','values-file']: p.add_argument('--'+key)
    p.add_argument('--submission-started',action='store_true')
    a=vars(p.parse_args());path=a.pop('manifest')
    data=update_manifest(path,**a)
    print(json.dumps({'manifest':str(path),'status':data['status']}))

if __name__=='__main__':
    try: main()
    except (ValueError,OSError,KeyError) as e:
        print(f'error: {e}',file=sys.stderr);sys.exit(1)

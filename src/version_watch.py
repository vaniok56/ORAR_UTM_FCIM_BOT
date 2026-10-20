"""Daily official-PDF observations; never imports or publishes a timetable."""
import asyncio
import datetime as dt
import hashlib
import html
import json
import re
import time
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests
import handlers.db as db
from functions import send_logs

ZONE = ZoneInfo('Europe/Chisinau')
LANDING = 'https://fcim.utm.md/procesul-de-studii/orar/'
YEARS = {'Anul I': 1, 'Anul II': 2, 'Anul III': 3, 'Anul IV': 4}
_watch_lock = asyncio.Lock()


def official_url(url, *, pdf=False):
    if not isinstance(url, str):
        raise ValueError('Official URL must be text')
    parsed = urlsplit(url)
    pattern = (r'/wp-content/uploads/sites/24/\d{4}/\d{2}/anul_(i|ii|iii|iv)_semestrul_[ivx]+(?:-\d+)?\.pdf'
               if pdf else r'/(?:procesul-de-studii/orar|orar-sectia-zi(?:-\d+)?)/')
    if (parsed.scheme != 'https' or parsed.netloc != 'fcim.utm.md' or parsed.query
            or parsed.fragment or len(url) > 255 or not re.fullmatch(pattern, parsed.path, re.I)):
        raise ValueError('Unexpected official URL')
    return url


def interactive_url(page):
    for row in re.findall(r'<tr\b[^>]*>.*?</tr\s*>', page, re.I | re.S):
        text = html.unescape(re.sub(r'<[^>]*>', ' ', row))
        if 'orar semestrul de' not in ' '.join(text.lower().split()):
            continue
        links = {urljoin(LANDING, html.unescape(link))
                 for link in re.findall(r'\s+href\s*=\s*["\']([^"\']+)["\']', row, re.I)}
        if len(links) != 1:
            raise ValueError('Ambiguous current timetable row')
        link = links.pop()
        if 'orar-sectia-zi' not in urlsplit(link).path:
            raise ValueError('Full-time timetable link unavailable')
        return official_url(link)
    raise ValueError('Current full-time timetable row unavailable')


def pdf_mapping(page):
    assignments = list(re.finditer(r'\bwindow\.ORAR_FCIM_EXCEL\s*=\s*', page))
    if len(assignments) != 1:
        raise ValueError('Official PDF mapping missing or ambiguous')

    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError('Duplicate mapping year')
        return result

    literal = page[assignments[0].end():]
    mapping, end = json.JSONDecoder(object_pairs_hook=unique).raw_decode(literal)
    if (not re.match(r'\s*;\s*</script\s*>', literal[end:], re.I)
            or not isinstance(mapping, dict) or set(mapping) != set(YEARS)):
        raise ValueError('Expected a literal four-year PDF mapping')
    for name, url in mapping.items():
        official_url(url, pdf=True)
        if not urlsplit(url).path.rsplit('/', 1)[1].lower().startswith(f'anul_{name.split()[1].lower()}_semestrul_'):
            raise ValueError('PDF year differs from mapping')
    return {year: mapping[name] for name, year in YEARS.items()}


def fetch(url, *, pdf=False):
    official_url(url, pdf=pdf)
    limit = 20 * 1024 * 1024 if pdf else 2 * 1024 * 1024
    started = time.monotonic()
    with requests.get(url, timeout=(8, 15), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200 or response.headers.get('Content-Type', '').split(';')[0].lower() != (
                'application/pdf' if pdf else 'text/html'):
            raise ValueError('Unexpected official response')
        data = bytearray()
        for chunk in response.iter_content(65536):
            if len(data) + len(chunk) > limit or time.monotonic() - started > 45:
                raise ValueError('Official response exceeds download budget')
            data.extend(chunk)
    if pdf and not data.startswith(b'%PDF-'):
        raise ValueError('Response is not a PDF')
    return hashlib.sha256(data).hexdigest() if pdf else data.decode('utf-8')


def next_check(now):
    local = now.astimezone(ZONE)
    day = local.date() + dt.timedelta(days=local.hour >= 18)
    return dt.datetime.combine(day, dt.time(18), ZONE)


def save_observation(source, at, *, url=None, fingerprint=None, error=None):
    settings = db.get_app_settings('fcim_')
    state_key = f'fcim_state_{source}'
    state = json.loads(settings.get(state_key, '{}'))
    values = {}

    def notice(kind):
        key = f'fcim_notice_{at[:10]}_{source}_{kind}'
        values[key] = json.dumps({'source': source, 'kind': kind, 'at': at}, separators=(',', ':'))
        if url:
            values[key.replace('notice', 'link', 1)] = url

    if error:
        state['f'] = min(state.get('f', 0) + 1, 9999)
        state['error'] = type(error).__name__
        if state['f'] >= 2 and not state.get('outage'):
            notice('outage')
            state['outage'] = 'pending'
    else:
        if state.get('outage') == 'sent':
            notice('recovery')
        elif state.get('outage') == 'pending':
            for key in settings:
                if key.startswith('fcim_notice_') and key.endswith(f'_{source}_outage'):
                    values.update({key: None, key.replace('notice', 'link', 1): None})
        state.update(f=0, outage=False, error=None, ok=at)
        if fingerprint:
            old_hash = settings.get(f'fcim_hash_{source}')
            if old_hash and (old_hash != fingerprint or settings.get(f'fcim_url_{source}') != url):
                notice('change')
            values.update({f'fcim_hash_{source}': fingerprint, f'fcim_url_{source}': url})
    values[state_key] = json.dumps(state, separators=(',', ':'))
    db.set_app_settings(values)


async def _check(now):
    at = now.astimezone(ZONE).isoformat(timespec='seconds')
    if not db.claim_watch_date(at[:10]):
        return False
    try:
        page = await asyncio.to_thread(fetch, LANDING)
        mapping = pdf_mapping(await asyncio.to_thread(fetch, interactive_url(page)))
    except Exception as error:
        send_logs(f'FCIM discovery unavailable: {type(error).__name__}', 'warning')
        save_observation('source', at, error=error)
    else:
        save_observation('source', at)
        for year, url in mapping.items():
            try:
                fingerprint = await asyncio.to_thread(fetch, url, pdf=True)
            except Exception as error:
                send_logs(f'FCIM year {year} unavailable: {type(error).__name__}', 'warning')
                save_observation(str(year), at, error=error)
            else:
                save_observation(str(year), at, url=url, fingerprint=fingerprint)
    db.set_app_settings({'fcim_run': 'complete'})
    return True


async def _send_pending(client):
    settings = db.get_app_settings('fcim_')
    notices = sorted(k for k in settings if k.startswith('fcim_notice_'))
    if not notices:
        return
    owner = settings.get('fcim_owner_id', '')
    if not owner.isdecimal() or int(owner) <= 0:
        raise ValueError('Configure explicit fcim_owner_id before enabling the monitor')
    for key in notices:
        item = json.loads(settings[key])
        source, kind, at = item['source'], item['kind'], item['at']
        label = 'discovery source' if source == 'source' else f'year {source}'
        link_key = key.replace('notice', 'link', 1)
        url = settings.get(link_key, LANDING)
        official_url(url, pdf=url != LANDING)
        text = {'change': 'official PDF changed; review needed before manual publication.',
                'outage': 'unavailable for two consecutive scheduled checks.',
                'recovery': 'recovered after the reported outage.'}[kind]
        await client.send_message(int(owner), f'FCIM {label}: {text}\nObserved: {at}\n{url}',
                                  parse_mode=None, link_preview=False)
        # shortcut: send/delete cannot be atomic; a crash here can repeat this notice.
        values = {key: None, link_key: None}
        if kind == 'outage':
            state_key = f'fcim_state_{source}'
            state = json.loads(db.get_app_setting(state_key, '{}', strict=True))
            if state.get('f', 0) == 0:
                # Recovery may have happened while Telegram was sending this outage.
                values[f"fcim_notice_{state['ok'][:10]}_{source}_recovery"] = json.dumps(
                    {'source': source, 'kind': 'recovery', 'at': state['ok']}, separators=(',', ':'))
            else:
                state['outage'] = 'sent'
            values[state_key] = json.dumps(state, separators=(',', ':'))
        db.set_app_settings(values)


async def check(now):
    async with _watch_lock:
        return await _check(now)


async def send_pending(client):
    async with _watch_lock:
        return await _send_pending(client)


async def retry_notices(client):
    while True:
        try:
            await send_pending(client)
        except Exception as error:
            send_logs(f'FCIM notice retry pending: {type(error).__name__}', 'warning')
        await asyncio.sleep(60)


async def run(client):
    target = next_check(dt.datetime.now(ZONE))
    notices = asyncio.create_task(retry_notices(client))
    try:
        while True:
            try:
                now = dt.datetime.now(ZONE)
                if now >= target:
                    if (now - target).total_seconds() < 60:
                        await check(now)
                    target = next_check(dt.datetime.now(ZONE))
                await asyncio.sleep(min(60, max(1, (target - dt.datetime.now(ZONE)).total_seconds())))
            except Exception as error:
                send_logs(f'FCIM monitor error: {type(error).__name__}', 'error')
                target = next_check(dt.datetime.now(ZONE))
                await asyncio.sleep(60)
    finally:
        notices.cancel()
        await asyncio.gather(notices, return_exceptions=True)


def _pdf_label(url):
    match = re.search(r'-(\d+)\.pdf$', url or '', re.I)
    return f'v{match.group(1)}' if match else 'final' if url else '?'


def _clock(iso):
    try:
        return dt.datetime.fromisoformat(iso).strftime('%d.%m %H:%M')
    except (TypeError, ValueError):
        return '?'


def version_text(local_versions, now=None):
    now = (now or dt.datetime.now(ZONE)).astimezone(ZONE)
    expected = (now.date() - dt.timedelta(days=now.hour < 18)).isoformat()
    try:
        settings = db.get_app_settings('fcim_')
        source = json.loads(settings.get('fcim_state_source', '{}'))
    except Exception as error:
        send_logs(f'FCIM cached status unavailable: {type(error).__name__}', 'warning')
        settings, source = {}, {'error': True}
    lines = ['Schedule (local / web):']
    missing, checked, stale = [], [], False
    for year, version in local_versions.items():
        local = 'missing' if version is None else f'v{version}' if isinstance(version, int) else str(version)
        web = _pdf_label(settings.get(f'fcim_url_{year}'))
        try:
            state = json.loads(settings.get(f'fcim_state_{year}', '{}'))
        except (TypeError, ValueError):
            state = {'error': True}
        if source.get('error') or state.get('error') or settings.get('fcim_run') == 'incomplete' or not state.get('ok'):
            web = '?'
            missing.append(str(year))
        else:
            checked.append(state['ok'])
            stale = stale or state['ok'][:10] < expected
        mark = ''
        if local.startswith('v') and web.startswith('v') and local[1:].isdigit() and web[1:].isdigit():
            mark = ' ✅' if int(local[1:]) == int(web[1:]) else ' ❌'
        elif local == web == 'final':
            mark = ' ✅'
        lines.append(f'{year}: {local} / {web}{mark}')
    if source.get('error'):
        lines.append('Web unavailable')
    elif settings.get('fcim_run') == 'incomplete':
        lines.append('Web check interrupted')
    elif not checked:
        lines.append('Web not checked yet')
    elif missing:
        lines.append(f'Web missing for: {",".join(missing)}')
    elif stale:
        lines.append(f'Web check stale (last {_clock(max(checked))})')
    return '\n'.join(lines) + '\n'

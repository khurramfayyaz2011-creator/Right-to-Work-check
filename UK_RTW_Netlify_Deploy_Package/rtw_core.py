"""
UK Right to Work (RTW) Verification Core Engine
High-performance thread-safe automated checker against UK Home Office service.
Extracts verified name, photo, status, visa expiry, conditions, restrictions, reference number,
and specifically parsed 'allowed_hours' (e.g. 20 hours, 10 hours, full time).
"""

import urllib.request
import urllib.parse
import http.cookiejar
import re
import html
import base64
import time
import threading
from datetime import datetime

def extract_working_hours(conditions, status, summary):
    if not status or 'mismatch' in status.lower() or 'invalid' in status.lower() or 'error' in status.lower():
        return 'N/A (Mismatch / Invalid)'

    text = " ".join(conditions or []).lower() + " " + str(summary or '').lower()
    
    if '20 hour' in text or '20 hrs' in text or 'twenty hour' in text:
        return '20 hrs/week (Term-time) / Full-time (Holidays)'
    elif '10 hour' in text or '10 hrs' in text or 'ten hour' in text:
        return '10 hrs/week (Term-time) / Full-time (Holidays)'
    elif 'continuous' in str(status).lower() or 'no limit' in text or 'indefinite' in text:
        return 'Full-time (No Limit)'
    elif 'no work' in text or 'prohibited' in text:
        return 'No Work Permitted'
    elif 'limited' in str(status).lower():
        m = re.search(r'(\d{1,2})\s*hours?', text)
        if m:
            return f"Up to {m.group(1)} hrs/week"
        return 'Full-time (Subject to visa conditions)'
    return 'Full-time'

class UKRightToWorkChecker:
    def __init__(self, company_name="HR Compliance Department", timeout=12):
        self.company_name = company_name
        self.timeout = timeout
        self.cache = {}
        self.lock = threading.Lock()

    @staticmethod
    def normalize_share_code(code: str) -> str:
        if not code:
            return ""
        return re.sub(r'[^A-Za-z0-9]', '', str(code)).upper()

    @staticmethod
    def parse_dob(dob_raw: str):
        if not dob_raw:
            return None
        s = str(dob_raw).strip()
        
        formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%Y/%m/%d',
            '%d %b %Y',
            '%d %B %Y',
            '%d.%m.%Y'
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(s, fmt)
                return str(dt.day), str(dt.month), str(dt.year)
            except ValueError:
                continue
                
        m_iso = re.match(r'^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$', s)
        if m_iso:
            y, m, d = m_iso.groups()
            return str(int(d)), str(int(m)), y
            
        m_uk = re.match(r'^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$', s)
        if m_uk:
            d, m, y = m_uk.groups()
            return str(int(d)), str(int(m)), y

        return None

    def check_staff(self, name: str, share_code: str, dob: str, company: str = None) -> dict:
        checker_company = (company or self.company_name or 'HR Compliance Department').strip()
        clean_code = self.normalize_share_code(share_code)
        parsed_dob = self.parse_dob(dob)

        result = {
            'input_name': name.strip() if name else '',
            'input_share_code': share_code,
            'clean_share_code': clean_code,
            'input_dob': dob,
            'employer': checker_company,
            'verified_name': '',
            'status': 'Pending',
            'allowed_hours': 'Pending',
            'visa_expiry': '',
            'valid_from': '',
            'rtw_summary': '',
            'conditions': [],
            'restrictions': [],
            'reference_number': '',
            'check_date': datetime.now().strftime('%d %B %Y'),
            'company_name': checker_company,
            'photo_base64': '',
            'photo_bytes': None,
            'success': False,
            'error_message': ''
        }

        if not clean_code:
            result['status'] = 'Invalid Code'
            result['allowed_hours'] = 'N/A (Invalid Code)'
            result['error_message'] = 'Missing or invalid share code.'
            return result

        if not parsed_dob:
            result['status'] = 'Invalid DOB'
            result['allowed_hours'] = 'N/A (Invalid DOB)'
            result['error_message'] = f'Could not parse date of birth: "{dob}". Expected YYYY-MM-DD or DD/MM/YYYY.'
            return result

        day, month, year = parsed_dob
        cache_key = (clean_code, f"{year}-{month.zfill(2)}-{day.zfill(2)}", checker_company.lower())
        
        with self.lock:
            if cache_key in self.cache:
                cached = dict(self.cache[cache_key])
                cached['input_name'] = result['input_name']
                cached['employer'] = checker_company
                cached['company_name'] = checker_company
                return cached

        cookie_jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.9',
        }

        try:
            # Step 1: GET Start Page
            req1 = urllib.request.Request('https://right-to-work.service.gov.uk/rtw-view', headers=headers)
            with opener.open(req1, timeout=self.timeout) as resp1:
                page1 = resp1.read().decode('utf-8')
                action_match1 = re.search(r'<form[^>]*action=[\'"]([^\'"]*)[\'"]', page1, re.I)
                if not action_match1:
                    result['status'] = 'Service Error'
                    result['allowed_hours'] = 'N/A'
                    result['error_message'] = 'Could not locate initial login form on gov.uk.'
                    return result
                form_action1 = html.unescape(action_match1.group(1))

            # Step 2: POST Share Code
            post_code_data = urllib.parse.urlencode({'shareCode': clean_code}).encode('utf-8')
            req2 = urllib.request.Request(form_action1, data=post_code_data, headers={
                **headers,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://user-auth.apply-to-visit-or-stay-in-the-uk.homeoffice.gov.uk',
                'Referer': resp1.geturl()
            })
            with opener.open(req2, timeout=self.timeout) as resp2:
                page2 = resp2.read().decode('utf-8')
                action_match2 = re.search(r'<form[^>]*action=[\'"]([^\'"]*)[\'"]', page2, re.I)
                if not action_match2:
                    result['status'] = 'Invalid Code'
                    result['allowed_hours'] = 'N/A (Invalid Code)'
                    result['error_message'] = 'Share code not recognized or expired.'
                    return result
                form_action2 = html.unescape(action_match2.group(1))

            # Step 3: POST Date of Birth
            post_dob_data = urllib.parse.urlencode({
                'dob-day': day,
                'dob-month': month,
                'dob-year': year
            }).encode('utf-8')
            req3 = urllib.request.Request(form_action2, data=post_dob_data, headers={
                **headers,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://user-auth.apply-to-visit-or-stay-in-the-uk.homeoffice.gov.uk',
                'Referer': resp2.geturl()
            })
            with opener.open(req3, timeout=self.timeout) as resp3:
                page3 = resp3.read().decode('utf-8')
                page3_url = resp3.geturl()

                if "Details do not match our records" in page3 or "Error: Please check your details" in page3:
                    result['status'] = 'Details Mismatch'
                    result['allowed_hours'] = 'N/A (Mismatch)'
                    result['error_message'] = 'Share code and date of birth do not match Home Office records.'
                    return result

                csrf_match = re.search(r'name=[\'"]x-csrf-token[\'"]\s+value=[\'"]([^\'"]*)[\'"]', page3, re.I)
                if not csrf_match:
                    result['status'] = 'Session Error'
                    result['allowed_hours'] = 'N/A'
                    result['error_message'] = 'Could not retrieve employer verification security token.'
                    return result
                csrf_token = csrf_match.group(1)

            # Step 4: POST Employer Company Name
            post_comp_data = urllib.parse.urlencode({
                'checkerName': checker_company,
                'x-csrf-token': csrf_token
            }).encode('utf-8')
            req4 = urllib.request.Request(page3_url, data=post_comp_data, headers={
                **headers,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://right-to-work.service.gov.uk',
                'Referer': page3_url
            })

            with opener.open(req4, timeout=self.timeout) as resp4:
                page4 = resp4.read().decode('utf-8')
                self._parse_success_profile(page4, result)
                result['company_name'] = checker_company
                result['employer'] = checker_company
                result['allowed_hours'] = extract_working_hours(result['conditions'], result['status'], result['rtw_summary'])
                result['success'] = True
                
                with self.lock:
                    self.cache[cache_key] = result
                return result

        except Exception as e:
            result['status'] = 'Connection Error'
            result['allowed_hours'] = 'N/A'
            result['error_message'] = f'Network or service error: {str(e)}'
            return result

    def _parse_success_profile(self, page_html: str, result: dict):
        img_match = re.search(r'id=[\'"]profileImage[\'"][^>]*src=[\'"]data:image/jpeg;base64,([^\'"]+)[\'"]', page_html)
        if not img_match:
            img_match = re.search(r'src=[\'"]data:image/[^;]+;base64,([^\'"]+)[\'"]', page_html)
        if img_match:
            b64_str = img_match.group(1)
            result['photo_base64'] = b64_str
            try:
                result['photo_bytes'] = base64.b64decode(b64_str)
            except Exception:
                pass

        main_match = re.search(r'<main[^>]*>(.*?)</main>', page_html, re.I | re.S)
        main_html = main_match.group(1) if main_match else page_html

        h2_matches = re.findall(r'<h2[^>]*>(.*?)</h2>', main_html, re.I | re.S)
        for h in h2_matches:
            h_clean = re.sub(r'<[^>]+>', '', h).strip()
            if h_clean and h_clean.upper() not in [
                'CONDITIONS', 'RESTRICTIONS', 'DETAILS OF CHECK',
                'COOKIES ON UK VISAS AND IMMIGRATION SERVICES',
                'CHANGE YOUR COOKIE SETTINGS', 'SUPPORT LINKS'
            ]:
                result['verified_name'] = h_clean
                break
        if not result['verified_name']:
            result['verified_name'] = result['input_name']

        summary_match = re.search(r'They have the right to work in the UK[^<.]*(?:\.[^<.]*)*\.', main_html, re.I)
        if summary_match:
            result['rtw_summary'] = re.sub(r'\s+', ' ', summary_match.group(0)).strip()

        from_match = re.search(r'from\s+([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})', main_html, re.I)
        if from_match:
            result['valid_from'] = from_match.group(1)

        until_match = re.search(r'until\s+([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})', main_html, re.I)
        if until_match:
            result['visa_expiry'] = until_match.group(1)
            result['status'] = f"Limited (until {result['visa_expiry']})"
        elif 'continuous' in main_html.lower() or 'no limit' in main_html.lower():
            result['visa_expiry'] = 'Continuous / Indefinite'
            result['status'] = 'Continuous Right to Work'
        else:
            result['visa_expiry'] = 'Verified'
            result['status'] = 'Right to Work Verified'

        ref_match = re.search(r'Reference number\s*[\r\n\s]+([A-Z0-9-]+)', re.sub(r'<[^>]+>', '\n', main_html), re.I)
        if ref_match:
            result['reference_number'] = ref_match.group(1).strip()

        date_match = re.search(r'Date of check\s*[\r\n\s]+([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})', re.sub(r'<[^>]+>', '\n', main_html), re.I)
        if date_match:
            result['check_date'] = date_match.group(1).strip()

        comp_match = re.search(r'Company name\s*[\r\n\s]+([^\r\n]+)', re.sub(r'<[^>]+>', '\n', main_html), re.I)
        if comp_match:
            result['company_name'] = comp_match.group(1).strip()

        cond_match = re.search(r'<h2[^>]*>\s*Conditions\s*</h2>(.*?)(?=<h2|$)', main_html, re.I | re.S)
        if cond_match:
            cond_html = cond_match.group(1)
            items = re.findall(r'<li[^>]*>(.*?)</li>', cond_html, re.I | re.S)
            if items:
                result['conditions'] = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', it)).strip() for it in items]
            else:
                raw_c = re.sub(r'<[^>]+>', '\n', cond_html)
                result['conditions'] = [re.sub(r'\s+', ' ', l).strip() for l in raw_c.splitlines() if re.sub(r'\s+', ' ', l).strip()]

        rest_match = re.search(r'<h2[^>]*>\s*Restrictions\s*</h2>(.*?)(?=<h2|$)', main_html, re.I | re.S)
        if rest_match:
            rest_html = rest_match.group(1)
            items = re.findall(r'<li[^>]*>(.*?)</li>', rest_html, re.I | re.S)
            if items:
                result['restrictions'] = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', it)).strip() for it in items]
            else:
                raw_r = re.sub(r'<[^>]+>', '\n', rest_html)
                result['restrictions'] = [re.sub(r'\s+', ' ', l).strip() for l in raw_r.splitlines() if re.sub(r'\s+', ' ', l).strip()]

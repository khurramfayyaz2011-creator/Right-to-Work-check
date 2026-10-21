"""
Official UK Home Office Right to Work High-Speed PDF Renderer
Matches 100% the official UK Home Office printout layout:
- Uses the authentic UK Home Office logo PNG (300x86) directly from Gov.UK
- Authentic GOV.UK checkbox PNG (30x30)
- Exact 2-column header (photo left 171.5pt, conditions right 360pt)
- Exact font sizes (Open Sans 16.5pt name, 13.5pt headers, 12pt subheaders, 10.5pt body)
- Full width restrictions and divider lines
- 2-column statutory excuse checklist and Details of Check box
- Strictly excludes mismatched/failed staff from PDF generation
- Generates separate merged PDF for each employer
"""

import os
import subprocess
import pymupdf
from govuk_assets import HO_OFFICIAL_LOGO_B64, HO_CHECKBOX_B64

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.environ.get("CHROME_BIN", ""),
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable"
]

def get_browser_exe():
    for p in EDGE_PATHS:
        if os.path.exists(p):
            return p
    return None

CSS_STYLES = """
@import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;700&display=swap');

@page {
    size: A4 portrait;
    margin: 11.25pt 15.0pt 15.0pt 15.0pt;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    font-family: 'Open Sans', Arial, sans-serif;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}

body {
    color: #000000;
    background: #ffffff;
    font-size: 10.5pt;
    line-height: 1.35;
}

.candidate-page-unit {
    width: 100%;
    page-break-after: always;
}

/* Authentic Official Home Office Logo */
.ho-logo-img {
    width: 93.75pt;
    height: 26.85pt;
    display: block;
    margin-bottom: 24pt;
}

/* Top 2-Column Section: Photo Left (171.5pt), Text Right (360pt) */
.top-section-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 12pt;
}

.top-section-table td {
    vertical-align: top;
    padding: 0;
}

.photo-cell {
    width: 171.5pt;
    padding-left: 7.5pt !important;
    padding-right: 15.0pt !important;
}

.candidate-photo {
    width: 171.5pt;
    height: 228.7pt;
    object-fit: cover;
    display: block;
}

.content-cell {
    width: 360pt;
}

h1.candidate-name {
    font-size: 16.5pt;
    font-weight: 600;
    text-transform: uppercase;
    line-height: 1.2;
    margin-bottom: 10pt;
    color: #000000;
}

p.statement {
    font-size: 10.5pt;
    line-height: 1.35;
    margin-bottom: 12pt;
    color: #000000;
}

h2.section-header {
    font-size: 13.5pt;
    font-weight: 600;
    margin-top: 10pt;
    margin-bottom: 8pt;
    color: #000000;
}

h3.sub-header {
    font-size: 12.0pt;
    font-weight: 600;
    margin-top: 8pt;
    margin-bottom: 6pt;
    color: #000000;
}

p.body-text {
    font-size: 10.5pt;
    line-height: 1.35;
    margin-bottom: 6pt;
}

ul.bullet-list {
    margin: 0 0 8pt 15pt;
    padding: 0;
}

ul.bullet-list li {
    font-size: 10.5pt;
    line-height: 1.35;
    margin-bottom: 3pt;
}

hr.divider-line {
    border: none;
    border-top: 0.75pt solid #979797;
    margin: 14pt 0 10pt 0;
    width: 100%;
}

/* Restrictions Section */
.restrictions-container {
    width: 100%;
}

/* Bottom 2-Column Section */
.bottom-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 2pt;
}

.bottom-table td {
    vertical-align: top;
    padding: 0;
}

.employ-cell {
    padding-right: 18.0pt;
}

.details-cell {
    width: 147.0pt;
}

.details-box {
    background: #F8F8F8;
    border: 0.75pt solid #BFBFBF;
    padding: 14pt 15.75pt;
    width: 147.0pt;
}

.details-box h3 {
    font-size: 13.5pt;
    font-weight: 600;
    margin-top: 0;
    margin-bottom: 10pt;
    color: #000000;
}

.detail-label {
    font-size: 9.8pt;
    font-weight: 600;
    color: #000000;
    margin-top: 8pt;
    margin-bottom: 2pt;
}

.detail-label:first-of-type {
    margin-top: 0;
}

.detail-val {
    font-size: 9.0pt;
    font-weight: 400;
    color: #000000;
    margin-bottom: 6pt;
}

.checkbox-row {
    display: flex;
    align-items: flex-start;
    margin-bottom: 8pt;
}

.box-img {
    width: 22.5pt;
    height: 22.5pt;
    flex-shrink: 0;
    margin-right: 8pt;
}

.box-label {
    font-size: 10.5pt;
    line-height: 1.35;
    color: #000000;
    padding-top: 2pt;
}

a {
    color: #0000FF;
    text-decoration: underline;
}
"""

def build_candidate_html(r):
    name = r.get('verified_name') or r.get('input_name') or 'Candidate'
    photo = r.get('photo_base64') or ''
    summary = r.get('rtw_summary') or 'They have the right to work in the UK.'
    expiry = r.get('visa_expiry') or 'Continuous'
    company = r.get('company_name') or r.get('employer') or 'Sample LTD'
    check_date = r.get('check_date') or ''
    ref_num = r.get('reference_number') or '-'

    photo_tag = f'<img src="data:image/jpeg;base64,{photo}" class="candidate-photo" />' if photo else '<div style="width:171.5pt; height:228.7pt; background:#e2e8f0; display:flex; align-items:center; justify-content:center; font-size:11pt; color:#64748b;">No Photo</div>'

    html = f"""
    <div class="candidate-page-unit">
        <img src="data:image/png;base64,{HO_OFFICIAL_LOGO_B64}" class="ho-logo-img" alt="Home Office" />

        <table class="top-section-table">
            <tr>
                <td class="photo-cell">
                    {photo_tag}
                </td>
                <td class="content-cell">
                    <h1 class="candidate-name">{name}</h1>
                    <p class="statement">{summary}</p>

                    <h2 class="section-header">Conditions</h2>

                    <h3 class="sub-header">While their visa is valid</h3>
                    <p class="body-text">They can work:</p>
                    <ul class="bullet-list">
                        <li>up to 20 hours a week during term time</li>
                        <li>full-time during periods outside of term time</li>
                    </ul>
                    <p class="body-text">They must share proof of their term dates with you.</p>

                    <h3 class="sub-header">Work placement</h3>
                    <p class="body-text">They can also work on a placement which is part of the course their student visa is based on. The work placement must be:</p>
                    <ul class="bullet-list">
                        <li>a compulsory part of their course</li>
                        <li>assessed as part of their course</li>
                    </ul>

                    <h3 class="sub-header">When they can start a permanent full-time job</h3>
                    <p class="body-text">If they apply for a Skilled Worker visa, they can start work in a permanent full-time job up to 3 months before their course completion date.</p>
                    <p class="body-text">If they apply for a Graduate visa, they can start work in a permanent full-time job once they have successfully completed their course of study.</p>
                    <p class="body-text">All of the following must also apply:</p>
                    <ul class="bullet-list">
                        <li>they are studying full-time at degree level or above with a higher education provider that has a <a href="https://www.gov.uk/government/publications/register-of-licensed-sponsors-students">track record of compliance as a student sponsor</a></li>
                        <li>they made a valid Skilled Worker or Graduate visa application when they had permission as a student</li>
                        <li>they are waiting for a decision on your Skilled Worker or Graduate visa application, or the outcome of any administrative review against a refusal</li>
                    </ul>
                </td>
            </tr>
        </table>

        <hr class="divider-line" />

        <div class="restrictions-container">
            <h2 class="section-header">Restrictions</h2>
            <p class="body-text">They cannot:</p>
            <ul class="bullet-list">
                <li>work as a professional sportsperson or sports coach</li>
                <li>work as an entertainer</li>
                <li>work in a position which would fill a permanent full-time vacancy unless they apply for a Skilled Worker or Graduate visa</li>
                <li>run a business or be self-employed - unless they have applied for a Start-up visa</li>
            </ul>
        </div>

        <hr class="divider-line" />

        <table class="bottom-table">
            <tr>
                <td class="employ-cell">
                    <h3 class="sub-header" style="margin-top: 0;">If you employ this person</h3>
                    <p class="body-text" style="margin-bottom: 10pt;">
                        <a href="https://www.gov.uk/government/publications/right-to-work-checks-employers-guide">To avoid a penalty</a>, you must:
                    </p>

                    <div class="checkbox-row">
                        <img src="data:image/png;base64,{HO_CHECKBOX_B64}" class="box-img" />
                        <div class="box-label">check this looks like the person you meet face to face or by video call</div>
                    </div>

                    <div class="checkbox-row">
                        <img src="data:image/png;base64,{HO_CHECKBOX_B64}" class="box-img" />
                        <div class="box-label">keep a secure copy of this online check (either electronically or in hard copy), for the duration of the employment and for 2 years after</div>
                    </div>

                    <div class="checkbox-row">
                        <img src="data:image/png;base64,{HO_CHECKBOX_B64}" class="box-img" />
                        <div class="box-label">get and keep details of their academic term and vacation times</div>
                    </div>

                    <p class="body-text" style="margin-top: 12pt;">
                        You must do this check again when their permission to be in the UK expires on {expiry}.
                    </p>
                    <p class="body-text" style="margin-top: 8pt;">
                        Read the <a href="https://www.gov.uk/government/publications/right-to-work-checks-employers-guide">employers' code of practice</a> to find out more about right to work checks.
                    </p>
                    <p class="body-text" style="margin-top: 8pt;">
                        You cannot accept a job applicant’s biometric residence card, biometric residence permit, or Frontier Worker permit as proof of their right to work. Ask them for a share code instead.
                    </p>
                </td>

                <td class="details-cell">
                    <div class="details-box">
                        <h3>Details of check</h3>
                        <div class="detail-label">Company name</div>
                        <div class="detail-val">{company}</div>
                        <div class="detail-label">Date of check</div>
                        <div class="detail-val">{check_date}</div>
                        <div class="detail-label">Reference number</div>
                        <div class="detail-val">{ref_num}</div>
                    </div>
                </td>
            </tr>
        </table>
    </div>
    """
    return html

def render_html_to_pdf(html_content, output_pdf_path):
    browser_exe = get_browser_exe()
    if not browser_exe:
        raise RuntimeError("No Chromium/Edge browser found for PDF rendering.")

    temp_html = output_pdf_path.replace('.pdf', '_temp.html')
    with open(temp_html, 'w', encoding='utf-8') as f:
        f.write(html_content)

    file_url = "file:///" + os.path.abspath(temp_html).replace("\\", "/")
    cmd = [
        browser_exe,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={os.path.abspath(output_pdf_path)}",
        file_url
    ]
    subprocess.run(cmd, check=True, timeout=90)
    if os.path.exists(temp_html):
        os.remove(temp_html)
    return output_pdf_path

def render_bulk_official_pdfs(records, output_dir, template_path=None):
    os.makedirs(output_dir, exist_ok=True)
    
    # Filter ONLY successfully matched staff
    matched_records = [
        r for r in records
        if r and r.get('success') is True and 'mismatch' not in str(r.get('status', '')).lower()
    ]

    if not matched_records:
        return None, {}, []

    # 1. Group matched staff by Employer
    records_by_employer = {}
    for r in matched_records:
        emp = (r.get('company_name') or r.get('employer') or 'Default_Employer').strip()
        records_by_employer.setdefault(emp, []).append(r)

    employer_pdf_map = {}
    all_individual_certs = []

    # 2. Render separate PDF for EACH Employer
    for employer_name, emp_records in records_by_employer.items():
        safe_emp = "".join([c if c.isalnum() else '_' for c in employer_name]).strip('_') or 'Employer'
        emp_pdf_filename = f"RTW_Certificates_{safe_emp}.pdf"
        emp_pdf_path = os.path.join(output_dir, emp_pdf_filename)

        body_content = "\n".join([build_candidate_html(r) for r in emp_records])
        master_html = f"""<!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <title>Right to Work Official Verifications - {employer_name}</title>
          <style>{CSS_STYLES}</style>
        </head>
        <body>
          {body_content}
        </body>
        </html>"""

        render_html_to_pdf(master_html, emp_pdf_path)
        employer_pdf_map[employer_name] = {
            'pdf_path': emp_pdf_path,
            'filename': emp_pdf_filename,
            'count': len(emp_records)
        }

        # Extract individual 2-page certs for this employer
        try:
            doc = pymupdf.open(emp_pdf_path)
            total_pages = len(doc)
            for idx, r in enumerate(emp_records, 1):
                clean_name = (r.get('verified_name') or r.get('input_name') or f'Staff_{idx}').replace(' ', '_')
                clean_name = "".join([c for c in clean_name if c.isalnum() or c in ('_', '-')])
                cert_filename = f"RTW_Certificate_{clean_name}_{safe_emp}.pdf"
                cert_path = os.path.join(output_dir, cert_filename)

                start_p = (idx - 1) * 2
                end_p = min(start_p + 1, total_pages - 1)

                if start_p < total_pages:
                    single_doc = pymupdf.open()
                    single_doc.insert_pdf(doc, from_page=start_p, to_page=end_p)
                    single_doc.save(cert_path)
                    single_doc.close()
                    all_individual_certs.append((cert_path, cert_filename, employer_name))
            doc.close()
        except Exception as e:
            print(f"Error splitting certs for {employer_name}:", e)

    # 3. Merged PDF with all verified staff
    all_pdf_path = os.path.join(output_dir, 'All_Verified_Staff_Official_Right_to_Work_Certificates.pdf')
    if len(records_by_employer) > 1:
        merged_all = pymupdf.open()
        for emp_info in employer_pdf_map.values():
            d = pymupdf.open(emp_info['pdf_path'])
            merged_all.insert_pdf(d)
            d.close()
        merged_all.save(all_pdf_path)
        merged_all.close()
    else:
        first_emp_info = list(employer_pdf_map.values())[0]
        all_pdf_path = first_emp_info['pdf_path']

    return all_pdf_path, employer_pdf_map, all_individual_certs

def render_single_official_pdf(record, output_pdf_path, template_path=None):
    if not record or not record.get('success') or 'mismatch' in str(record.get('status', '')).lower():
        return None

    single_html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <title>Right to Work Official Verification</title>
      <style>{CSS_STYLES}</style>
    </head>
    <body>
      {build_candidate_html(record)}
    </body>
    </html>"""

    return render_html_to_pdf(single_html, output_pdf_path)

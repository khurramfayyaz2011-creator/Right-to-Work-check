"""
UK Right to Work Checker - Modern High-Speed Web Application
Supports CSV, Excel (.xlsx, .xls), and text uploads.
Multi-threaded parallel execution (12 workers).
Both standard (/api/check-bulk) and live streaming (/api/check-bulk-stream) endpoints.
Exact Home Office official PDF layout:
- Skips generating PDFs for mismatched/failed staff
- Generates separate merged PDF for each employer
- Exports CSV with 'Allowed Working Hours' column (e.g. 20 hours, 10 hours, full time)
- Highlights mismatched staff
"""

import os
import io
import csv
import json
import zipfile
import traceback
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, jsonify, render_template, send_file, Response
import openpyxl

from rtw_core import UKRightToWorkChecker
from official_pdf_renderer import render_bulk_official_pdfs, render_single_official_pdf

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 64 MB max

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_HTML_PATH = os.path.join(BASE_DIR, 'official_rtw_template.html')
OUTPUT_DIR = os.path.join(BASE_DIR, 'generated_reports')
os.makedirs(OUTPUT_DIR, exist_ok=True)

LATEST_BATCH = {
    'results': [],
    'company': 'HR Compliance Department',
    'timestamp': None,
    'by_employer': {},
    'cert_paths': []
}

@app.after_request
def add_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.route('/favicon.ico')
def favicon():
    return '', 204

def extract_rows_from_excel(file_bytes):
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []

    header_idx = -1
    name_col, code_col, dob_col, emp_col = 0, 1, 2, -1

    for r_idx, row in enumerate(rows[:10]):
        row_str = " ".join([str(c or '').lower() for c in row])
        if any(w in row_str for w in ['name', 'share', 'code', 'dob', 'birth']):
            header_idx = r_idx
            for c_idx, cell in enumerate(row):
                c_lower = str(cell or '').lower().strip()
                if 'name' in c_lower:
                    name_col = c_idx
                elif 'share' in c_lower or 'code' in c_lower:
                    code_col = c_idx
                elif 'dob' in c_lower or 'birth' in c_lower:
                    dob_col = c_idx
                elif any(k in c_lower for k in ['employer', 'company', 'client', 'organization', 'checker']):
                    emp_col = c_idx
            break

    data_rows = rows[header_idx + 1:] if header_idx != -1 else rows
    result = []
    for r in data_rows:
        if not r or all(c is None or str(c).strip() == '' for c in r):
            continue
        
        name = str(r[name_col]).strip() if len(r) > name_col and r[name_col] is not None else ''
        code = str(r[code_col]).strip() if len(r) > code_col and r[code_col] is not None else ''
        
        raw_dob = r[dob_col] if len(r) > dob_col and r[dob_col] is not None else ''
        if isinstance(raw_dob, (datetime,)):
            dob_str = raw_dob.strftime('%Y-%m-%d')
        else:
            dob_str = str(raw_dob).strip()

        employer = str(r[emp_col]).strip() if emp_col != -1 and len(r) > emp_col and r[emp_col] is not None else ''

        if name or code:
            result.append({'name': name, 'share_code': code, 'dob': dob_str, 'employer': employer})

    return result

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload-file', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded.'}), 400

    f = request.files['file']
    filename = (f.filename or '').lower()
    file_bytes = f.read()

    try:
        staff_list = []
        if filename.endswith('.xlsx') or filename.endswith('.xlsm') or filename.endswith('.xls'):
            staff_list = extract_rows_from_excel(file_bytes)
        else:
            text = file_bytes.decode('utf-8', errors='replace')
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            
            header_idx = -1
            name_col, code_col, dob_col, emp_col = 0, 1, 2, -1
            for r_idx, row in enumerate(rows[:10]):
                row_str = " ".join([str(c).lower() for c in row])
                if any(w in row_str for w in ['name', 'share', 'code', 'dob', 'birth']):
                    header_idx = r_idx
                    for c_idx, cell in enumerate(row):
                        c_lower = str(cell).lower().strip()
                        if 'name' in c_lower:
                            name_col = c_idx
                        elif 'share' in c_lower or 'code' in c_lower:
                            code_col = c_idx
                        elif 'dob' in c_lower or 'birth' in c_lower:
                            dob_col = c_idx
                        elif any(k in c_lower for k in ['employer', 'company', 'client', 'organization', 'checker']):
                            emp_col = c_idx
                    break

            data_rows = rows[header_idx + 1:] if header_idx != -1 else rows
            for r in data_rows:
                if not r or len(r) < 2 or all(str(c).strip() == '' for c in r):
                    continue
                name = r[name_col].strip() if len(r) > name_col else ''
                code = r[code_col].strip() if len(r) > code_col else ''
                dob = r[dob_col].strip() if len(r) > dob_col else ''
                employer = r[emp_col].strip() if emp_col != -1 and len(r) > emp_col else ''
                if name or code:
                    staff_list.append({'name': name, 'share_code': code, 'dob': dob, 'employer': employer})

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(['Name', 'RTW Share Code', 'DOB', 'Employer'])
        for s in staff_list:
            writer.writerow([s['name'], s['share_code'], s['dob'], s.get('employer', '')])

        return jsonify({
            'success': True,
            'count': len(staff_list),
            'staff': staff_list,
            'csv_text': csv_buffer.getvalue()
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'Failed to process file: {str(e)}'}), 400

def run_parallel_checks(staff_list, default_company):
    checker = UKRightToWorkChecker(company_name=default_company)
    total = len(staff_list)
    results = [None] * total
    max_workers = min(12, max(4, total // 5)) if total > 4 else 4

    def do_check(index, item):
        name = str(item.get('name', '')).strip()
        share_code = str(item.get('share_code', '')).strip()
        dob = str(item.get('dob', '')).strip()
        staff_employer = str(item.get('employer', '')).strip() or default_company
        res = checker.check_staff(name, share_code, dob, company=staff_employer)
        client_res = {k: v for k, v in res.items() if k != 'photo_bytes'}
        return index, client_res

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(do_check, i, item): i
            for i, item in enumerate(staff_list)
        }
        for future in as_completed(future_to_idx):
            idx, client_res = future.result()
            results[idx] = client_res

    return results

def save_batch_and_render_pdfs(results, default_company):
    LATEST_BATCH['results'] = results
    LATEST_BATCH['company'] = default_company
    LATEST_BATCH['timestamp'] = datetime.now()

    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    batch_output_dir = os.path.join(OUTPUT_DIR, f'batch_{timestamp_str}')
    os.makedirs(batch_output_dir, exist_ok=True)

    # Render official PDFs (skips mismatches, groups by employer)
    all_pdf_path, employer_pdf_map, all_individual_certs = render_bulk_official_pdfs(results, batch_output_dir)
    LATEST_BATCH['consolidated_pdf'] = all_pdf_path
    LATEST_BATCH['by_employer'] = employer_pdf_map
    LATEST_BATCH['cert_paths'] = all_individual_certs

    # Generate CSV with 'Allowed Working Hours' and clear Mismatch highlight
    csv_path = os.path.join(batch_output_dir, f'Staff_RTW_Verified_{timestamp_str}.csv')
    fieldnames = ['Name', 'RTW Share Code', 'DOB', 'Employer', 'Allowed Working Hours', 'Visa Expiry', 'Status', 'Home Office Ref', 'Check Date']
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            if r:
                is_mismatch = not r.get('success') or 'mismatch' in str(r.get('status', '')).lower()
                status_str = f"⚠️ MISMATCH - Check Details with Candidate" if is_mismatch else r.get('status')
                expiry_str = "N/A - Review Required" if is_mismatch else (r.get('visa_expiry') or 'Continuous')
                hours_str = r.get('allowed_hours') or ('N/A (Mismatch)' if is_mismatch else 'Full-time')

                writer.writerow({
                    'Name': r.get('verified_name') or r.get('input_name'),
                    'RTW Share Code': r.get('input_share_code'),
                    'DOB': r.get('input_dob'),
                    'Employer': r.get('company_name') or r.get('employer'),
                    'Allowed Working Hours': hours_str,
                    'Visa Expiry': expiry_str,
                    'Status': status_str,
                    'Home Office Ref': r.get('reference_number') or '-',
                    'Check Date': r.get('check_date'),
                })
    LATEST_BATCH['csv_path'] = csv_path

    # Generate ZIP bundle organized by employer
    zip_path = os.path.join(batch_output_dir, f'Official_RTW_Bundle_{timestamp_str}.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(csv_path, arcname=os.path.basename(csv_path))
        if all_pdf_path and os.path.exists(all_pdf_path):
            zf.write(all_pdf_path, arcname="All_Verified_Staff_Official_Right_to_Work_Certificates.pdf")
        for emp_name, emp_info in employer_pdf_map.items():
            if os.path.exists(emp_info['pdf_path']):
                zf.write(emp_info['pdf_path'], arcname=f"By_Employer/{emp_info['filename']}")
        for cp, arc, emp_name in all_individual_certs:
            if os.path.exists(cp):
                safe_emp = "".join([c if c.isalnum() else '_' for c in emp_name]).strip('_')
                zf.write(cp, arcname=f"Individual_Certificates_{safe_emp}/{arc}")

    LATEST_BATCH['zip_path'] = zip_path
    return all_pdf_path

@app.route('/api/check-bulk', methods=['POST'])
def check_bulk():
    try:
        data = request.get_json(force=True)
        staff_list = data.get('staff', [])
        default_company = data.get('company_name', 'HR Compliance Department').strip() or 'HR Compliance Department'

        if not staff_list:
            return jsonify({'error': 'No staff records provided.'}), 400

        results = run_parallel_checks(staff_list, default_company)
        save_batch_and_render_pdfs(results, default_company)

        return jsonify({
            'success': True,
            'count': len(results),
            'results': results,
            'by_employer': {k: {'filename': v['filename'], 'count': v['count']} for k, v in LATEST_BATCH.get('by_employer', {}).items()},
            'has_audit_pdf': bool(LATEST_BATCH.get('consolidated_pdf')),
            'has_zip': True,
            'has_csv': True
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/check-bulk-stream', methods=['POST'])
def check_bulk_stream():
    data = request.get_json(force=True)
    staff_list = data.get('staff', [])
    default_company = data.get('company_name', 'HR Compliance Department').strip() or 'HR Compliance Department'

    if not staff_list:
        return Response("data: " + json.dumps({'error': 'No staff records provided'}) + "\n\n", mimetype='text/event-stream')

    def generate_events():
        checker = UKRightToWorkChecker(company_name=default_company)
        total = len(staff_list)
        results = [None] * total
        completed_count = 0
        max_workers = min(12, max(4, total // 5)) if total > 4 else 4

        def do_check(index, item):
            name = str(item.get('name', '')).strip()
            share_code = str(item.get('share_code', '')).strip()
            dob = str(item.get('dob', '')).strip()
            staff_employer = str(item.get('employer', '')).strip() or default_company
            res = checker.check_staff(name, share_code, dob, company=staff_employer)
            client_res = {k: v for k, v in res.items() if k != 'photo_bytes'}
            return index, client_res

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(do_check, i, item): i
                for i, item in enumerate(staff_list)
            }

            for future in as_completed(future_to_idx):
                idx, client_res = future.result()
                results[idx] = client_res
                completed_count += 1
                percent = int((completed_count / total) * 90)
                yield f"data: {json.dumps({'type': 'progress', 'completed': completed_count, 'total': total, 'percent': percent, 'item': client_res, 'index': idx})}\n\n"

        yield f"data: {json.dumps({'type': 'status', 'percent': 95, 'message': 'Generating official Home Office PDF documents by employer (skipping mismatches)...'})}\n\n"

        save_batch_and_render_pdfs(results, default_company)

        employer_summary = {k: {'filename': v['filename'], 'count': v['count']} for k, v in LATEST_BATCH.get('by_employer', {}).items()}

        yield f"data: {json.dumps({'type': 'done', 'percent': 100, 'count': len(results), 'results': results, 'by_employer': employer_summary})}\n\n"

    return Response(generate_events(), mimetype='text/event-stream')

@app.route('/api/download/audit-pdf')
def download_audit_pdf():
    pdf_path = LATEST_BATCH.get('consolidated_pdf')
    if pdf_path and os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=True, download_name="All_Verified_Staff_Official_Right_to_Work_Certificates.pdf")
    return jsonify({'error': 'No verified PDF generated (no matching staff found).'}), 404

@app.route('/api/download/employer-pdf/<path:emp_name>')
def download_employer_pdf(emp_name):
    emp_map = LATEST_BATCH.get('by_employer', {})
    decoded_name = urllib.parse.unquote(emp_name)
    target = emp_map.get(emp_name) or emp_map.get(decoded_name)
    if target and os.path.exists(target['pdf_path']):
        return send_file(target['pdf_path'], as_attachment=True, download_name=target['filename'])
    return jsonify({'error': f'No PDF found for employer "{emp_name}".'}), 404

@app.route('/api/download/csv')
def download_csv():
    csv_path = LATEST_BATCH.get('csv_path')
    if csv_path and os.path.exists(csv_path):
        return send_file(csv_path, as_attachment=True, download_name="Staff_Right_to_Work_Verified.csv")
    return jsonify({'error': 'No CSV generated yet.'}), 404

@app.route('/api/download/zip')
def download_zip():
    zip_path = LATEST_BATCH.get('zip_path')
    if zip_path and os.path.exists(zip_path):
        return send_file(zip_path, as_attachment=True, download_name="All_Staff_Official_RTW_Bundle.zip")
    return jsonify({'error': 'No bundle generated yet.'}), 404

@app.route('/api/download/certificate/<int:index>')
def download_certificate(index):
    results = LATEST_BATCH.get('results', [])
    if 0 <= index < len(results) and results[index]:
        r = results[index]
        if not r.get('success') or 'mismatch' in str(r.get('status', '')).lower():
            return jsonify({'error': 'No PDF generated for mismatched candidate.'}), 400

        clean_name = (r.get('verified_name') or r.get('input_name') or f'Staff_{index+1}').replace(' ', '_')
        clean_name = "".join([c for c in clean_name if c.isalnum() or c in ('_', '-')])
        cert_filename = f"Official_RTW_Certificate_{clean_name}_{index+1}.pdf"
        cert_path = os.path.join(OUTPUT_DIR, cert_filename)
        render_single_official_pdf(r, cert_path)
        return send_file(cert_path, as_attachment=True, download_name=cert_filename)

    return jsonify({'error': 'Certificate not found.'}), 404

if __name__ == '__main__':
    print("Starting High-Speed UK Right to Work Checker on http://127.0.0.1:5000 ...")
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)

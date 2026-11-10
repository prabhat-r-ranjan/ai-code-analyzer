"""Eight-tab reporting v2: concise summary, readable evidence and no invented topology."""
from __future__ import annotations
from collections import Counter
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ORDER = ['Description','Technologies','Up & Down Stream','Summary','Kubernetes LLD','Migration Findings','Runtime Workloads','Runtime Dependencies']
UP_HEADERS = ['Direction','Type','Service / Controller','Protocol / Method','Endpoint / Target','Source File','Evidence / Status']


def safe(value):
    if value is None: return ''
    text = str(value)
    return "'" + text if text.startswith(('=','+','-','@')) else text


def unique_names(items):
    return ', '.join(sorted({str(x.get('name')) for x in items if isinstance(x,dict) and x.get('name')}))


def unique_files(items):
    return ', '.join(sorted({str(x.get('source_file')) for x in items if isinstance(x,dict) and x.get('source_file')}))


def _upstream(wb, result):
    ws = wb['Up & Down Stream']
    # Keep existing controller, database and integration rows, but collapse exact duplicates.
    original = list(ws.values)[1:]
    ws.delete_rows(2, ws.max_row)
    seen = set()
    def append(row):
        row = tuple(safe(x) for x in row)
        if row not in seen:
            ws.append(row); seen.add(row)
    for row in original:
        if any(x not in (None,'') for x in row): append(row[:7])

    # Operation-level evidence: do not confuse client type with a verified target.
    for item in result.get('source_client_evidence') or []:
        client = item.get('client_type') or item.get('client_variable') or 'Unresolved client'
        operation = item.get('operation') or 'Unresolved operation'
        config = item.get('configuration_prefix_candidates') or []
        wiring = item.get('base_path_wiring_candidates') or []
        details = ['Source call candidate; runtime not verified']
        if item.get('line') is not None: details.append('Line: '+str(item['line']))
        if item.get('resolution'): details.append('Resolution: '+str(item['resolution']))
        if config: details.append('Configuration candidates: '+safe(config))
        if wiring: details.append('Base-path wiring candidates: '+safe(wiring))
        if item.get('validation_required'): details.append('Validate: '+str(item['validation_required']))
        # If an existing downstream analyzer row is the same file and operation, suppress the
        # generic duplicate only when it lacks a concrete endpoint/target.
        source_file = safe(item.get('source_file'))
        for row_idx in range(ws.max_row, 1, -1):
            row = [ws.cell(row_idx,c).value or '' for c in range(1,8)]
            if (row[0] in ('outbound_candidate','Outbound') and row[1] in ('RestTemplate','WebClient','OpenFeign','Java HttpClient')
                and row[5] == source_file and (not row[4] or row[4] == 'None')
                and (not row[3] or row[3] == operation)):
                seen.discard(tuple(str(x) for x in row)); ws.delete_rows(row_idx)
        append(['Outbound','Java API client call',client,operation,'Target URL unresolved',source_file,'\n'.join(details)])

    chains = result.get('end_to_end_dependencies') or []
    if chains:
        for chain in chains:
            cfg = chain.get('configuration') or {}; endpoint = cfg.get('database_endpoint') or {}
            workload = chain.get('application_workload') or {}; cm = cfg.get('configmap') or {}
            services = chain.get('database_service_candidates') or []
            db_workloads = chain.get('database_workload_candidates') or []
            pvcs = chain.get('pvc_candidates') or []
            secret_refs = chain.get('secret_references') or []
            target = f"{endpoint.get('host') or 'unknown'}:{endpoint.get('port') if endpoint.get('port') is not None else '?'}"
            evidence = [
                'Static dependency candidate; runtime not verified',
                'ConfigMap: '+str(cm.get('name') or 'unknown'),
                'Config key: '+str(cfg.get('key') or 'unknown'),
                'Database: '+str(endpoint.get('database_type') or 'unknown')+'/'+str(endpoint.get('database_name') or 'unknown'),
                'Kubernetes services: '+(unique_names(services) or 'unresolved'),
                'Service manifest files: '+(unique_files(services) or 'unresolved'),
                'Database workloads: '+(unique_names(db_workloads) or 'unresolved'),
                'Workload manifest files: '+(unique_files(db_workloads) or 'unresolved'),
                'PVCs: '+(unique_names(pvcs) or 'none found'),
                'Secrets referenced: '+(', '.join(sorted({str(x.get('resource_name')) for x in secret_refs if x.get('resource_name')})) or 'none found'),
                'Resolution: '+str(chain.get('resolution') or 'unresolved'),
                'Validation: '+str(chain.get('validation_required') or 'Required'),
            ]
            append(['Outbound','Database dependency chain',f"{workload.get('kind') or 'Workload'}/{workload.get('name') or 'unknown'}",chain.get('container'),target,cm.get('source_file') or workload.get('source_file'),'\n'.join(evidence)])
    else:
        # Preserve legacy chain data without exporting opaque JSON.
        legacy = wb['Dependency Chains'] if 'Dependency Chains' in wb.sheetnames else None
        if legacy:
            rows = list(legacy.values)
            if rows:
                headers = rows[0]
                for r in rows[1:]:
                    if not any(x is not None and str(x).strip() for x in r): continue
                    evidence = '\n'.join(f'{h}: {v}' for h,v in zip(headers,r) if h and v not in (None,''))
                    append(['Outbound','Database dependency chain',r[0] if len(r)>0 else '',r[1] if len(r)>1 else '',f'{r[5] or "unknown"}:{r[6] if r[6] is not None else "?"}' if len(r)>6 else '',r[11] if len(r)>11 and r[11] else (r[13] if len(r)>13 else ''),evidence])


def _runtime(result):
    runtime = result.get('runtime_assessment') or {}
    scope = runtime.get('application_scope') or result.get('application_scope') or {}
    collected = runtime.get('runtime_verified') is True or runtime.get('collection_status') == 'SUCCESS'
    return collected,scope


def _summary(wb,result):
    ws = wb['Summary']
    notes = {}
    if 'Assessment Notes' in wb.sheetnames:
        for row in list(wb['Assessment Notes'].values)[1:]:
            if row and row[0]: notes[str(row[0])] = row[1] if len(row)>1 else ''
    ws.delete_rows(2,ws.max_row)
    tech = result.get('technologies') or []
    app = tech[0].get('artifact_id') if tech else ''
    classified = [x for t in tech for x in (t.get('classified_technology') or [])]
    runtime,scope = _runtime(result)
    findings = result.get('migration_impact_findings') or []
    severity = Counter(str(f.get('severity') or '').lower() for f in findings)
    source = result.get('source_client_evidence') or []
    downstream = result.get('downstream_details') or []
    rows = [
        ('APPLICATION OVERVIEW',''),
        ('Application',app), ('Repository',result.get('repository')),('Branch',result.get('branch')),
        ('Automated Scan Status',result.get('status')),('Business Capability','Manual assessment required'),
        ('SOURCE ANALYSIS',''),
        ('POM Files',result.get('pom_count',len(result.get('pom_files') or []))),
        ('Classified Technologies',len(classified)),('Inbound REST APIs (declared)',len(result.get('api_endpoints') or [])),
        ('Actual Upstream Callers','Unknown — requires gateway/traces/cross-repository evidence'),
        ('Outbound Java Client Operations (detected)',len(source)),
        ('Other HTTP Candidates (detected)',len(downstream)),
        ('Database Configurations',len(result.get('database_details') or [])),
        ('Other Integration Findings',len(result.get('integration_details') or [])),
        ('KUBERNETES & RUNTIME',''),
        ('Manifest Definitions (static)',len(result.get('deployment_details') or [])),
        ('Runtime Inventory Collected',runtime),
        ('Selected Runtime Workload',scope.get('requested_workload') or scope.get('workload_name') or result.get('runtime_workload') or 'Not specified'),
        ('Runtime Scope Resolution',scope.get('status') or 'Not established'),
        ('Source-to-Runtime Provenance','Not verified'),
        ('Application Connectivity','Not tested'),
        ('MIGRATION ASSESSMENT',''),
        ('Migration Findings',len(findings)),
        ('Findings High / Medium / Low',f"{severity['high']} / {severity['medium']} / {severity['low']}"),
        ('Migration Readiness','Assessment in progress — no automatic readiness score'),
        ('Assessment Scope',notes.get('Analysis Scope') or 'Static repository/manifests plus optional read-only runtime inventory'),
        ('Evidence Limitation',notes.get('Important Limitation') or 'Static candidates are not verified runtime topology'),
        ('Deployment Validation',notes.get('Deployment Validation') or 'Confirm active Helm/Kustomize overlays and namespace'),
        ('Connectivity Validation',notes.get('Connectivity Validation') or 'Verify DNS, TCP, TLS and authentication'),
        ('Security',notes.get('Security') or 'Only reference names/keys; never export Secret values'),
    ]
    for label,value in rows: ws.append([safe(label),safe(value)])


def _format(ws):
    ws.freeze_panes='A2'; ws.sheet_view.showGridLines=False; ws.auto_filter.ref=ws.dimensions
    for c in ws[1]:
        c.fill=PatternFill('solid',fgColor='17365D'); c.font=Font(color='FFFFFF',bold=True); c.alignment=Alignment(wrap_text=True)
    for row in ws.iter_rows(min_row=2):
        for c in row: c.alignment=Alignment(vertical='top',wrap_text=True)
        if ws.title=='Summary' and row[0].value in ('APPLICATION OVERVIEW','SOURCE ANALYSIS','KUBERNETES & RUNTIME','MIGRATION ASSESSMENT'):
            for c in row: c.fill=PatternFill('solid',fgColor='DCEAF4'); c.font=Font(bold=True,color='17365D')
    if ws.title=='Up & Down Stream':
        for i in range(1,8): ws.column_dimensions[get_column_letter(i)].width=70 if i==7 else 35
        ws.row_dimensions[1].height=34
    else:
        ws.column_dimensions['A'].width=48; ws.column_dimensions['B'].width=86
        ws.row_dimensions[1].height=32


def finalize_eight_tab_workbook(wb,result):
    _upstream(wb,result)
    _summary(wb,result)
    for old in ('Dependency Chains','Assessment Notes'):
        if old in wb.sheetnames: del wb[old]
    for name in ORDER:
        if name not in wb.sheetnames:
            ws=wb.create_sheet(name)
            ws.append(['Runtime collection not included' if name.startswith('Runtime ') else 'No assessment data'])
    extra=set(wb.sheetnames)-set(ORDER)
    if extra: raise ValueError(f'Unexpected sheets: {sorted(extra)}')
    wb._sheets[:]=[wb[name] for name in ORDER]
    for name in ('Up & Down Stream','Summary'): _format(wb[name])
    assert wb.sheetnames==ORDER
    return wb

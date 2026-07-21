# -*- coding: utf-8 -*-
"""LIMS 工作液溯源链查询（从 D:\\...\\Management-of-Standard-Substance\\login_html.py 移植，无 Flask 依赖）。

只依赖一个「已登录 system 对象」（鸭子接口：.session / .base_url / .current_pid /
.current_real_name —— `lims_auto_login.LoginResult` 正好满足），外加 re/time 标准库。
不 import login_html，避免其 Flask 副作用。

入口：`trace_working_solution(code, system)` —— 给一个工作液编号(如 'D-9203')，返回
自上而下(A..B..C..D)的溯源链记录列表。每条记录字段见 `_trace_export_chain` 的 matched 字典。

下列函数为 login_html.py 原样拷贝（行号见各函数上方注释），保持与上游一致以便对照维护。
"""
import re
import time


# ===== 以下移植自 login_html.py（行号为移植时上游位置，便于对照） =====

def _parse_conc_field(conc_str):  # login_html.py:1579
    """Parse LIMS concentration field.
    '0.01(mg/L)' → (0.01, 'mg/L')
    'DIDP:447.10(mg/L);DINP:682.32(mg/L)' → [(DIDP,447.10,mg/L), ...]
    """
    if not conc_str:
        return []
    text = str(conc_str).strip()
    if ':' in text and ';' in text:
        parts = text.split(';')
        result = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            ci = p.rfind(':')
            if ci < 0:
                continue
            name = p[:ci].strip()
            cstr = p[ci+1:].strip()
            m = re.match(r'^([\d.]+)\s*\(([^)]+)\)', cstr)
            if m:
                result.append((name, float(m.group(1)), m.group(2)))
            else:
                m2 = re.match(r'^([\d.]+)\s*(\S+)', cstr)
                if m2:
                    result.append((name, float(m2.group(1)), m2.group(2)))
        return result
    m = re.match(r'^([\d.]+)\s*\(([^)]+)\)', text)
    if m:
        return [(None, float(m.group(1)), m.group(2))]
    m2 = re.match(r'^([\d.]+)\s*(\S+)', text)
    if m2:
        return [(None, float(m2.group(1)), m2.group(2))]
    return []


_order_to_id_cache = {}   # login_html.py:1616
_type_list_cache = {}     # login_html.py:1617


def _resolve_order_to_lims_id(system, configure_order):  # login_html.py:1619
    """Resolve configureOrder (e.g. 'B-3408') to actual LIMS record ID.
    Uses getSolutionAdata API with appropriate type parameter, pageSize=9999,
    exact matching, and per-type list caching."""
    global _order_to_id_cache, _type_list_cache
    if configure_order in _order_to_id_cache:
        return _order_to_id_cache[configure_order]
    parts = configure_order.split('-')
    if len(parts) < 2:
        return None
    prefix = parts[0].upper()
    if prefix == 'A':
        return None  # A-type records not queryable via this API
    type_map = {'B': 'SOLUTION_TYPE_B', 'C': 'SOLUTION_TYPE_C', 'D': 'SOLUTION_TYPE_D', 'E': 'SOLUTION_TYPE_E'}
    sol_type = type_map.get(prefix)
    if not sol_type:
        return None
    try:
        if sol_type in _type_list_cache:
            items = _type_list_cache[sol_type]
        else:
            url = f"{system.base_url}/detectionManager/manager/dtSolutionConfigure/getSolutionAdata"
            headers = {"Referer": f"{system.base_url}/web/solutionConfigure.html?menuId=544"}
            items = []
            page_no = 1
            while True:
                resp = system.session.get(url, params={
                    "type": sol_type, "pageSize": 9999, "pageNo": page_no,
                    "status": "1",
                    "pid": system.current_pid or '',
                    "pname": system.current_real_name or '',
                    "loginId": system.current_pid or '',
                }, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                page_items = data.get('resultData', {}).get('voList', [])
                items.extend(page_items)
                if not data.get('resultData', {}).get('hasNext', False):
                    break
                page_no += 1
            _type_list_cache[sol_type] = items
        # Exact match
        for item in items:
            order = str(item.get('configureOrder', '')).strip()
            if order == configure_order:
                lid = item.get('id')
                if lid:
                    _order_to_id_cache[configure_order] = lid
                    return lid
        # Prefix + number exact match (not endswith)
        order_num = parts[1].strip()
        for item in items:
            item_order = str(item.get('configureOrder', '')).strip()
            item_parts = item_order.split('-')
            if (len(item_parts) >= 2
                    and item_parts[0].upper() == prefix
                    and item_parts[1].strip() == order_num):
                lid = item.get('id')
                if lid:
                    _order_to_id_cache[configure_order] = lid
                    return lid
    except Exception as e:
        pass
    return None


def _resolve_by_solution_code(system, solution_code):  # login_html.py:1685
    """Resolve solutionCode (e.g. 'CK-CG-xxx') to (lims_id, configure_order) or (None, None).
    Uses getSolutionAdata with solutionCode parameter for precise search."""
    global _order_to_id_cache
    url = f"{system.base_url}/detectionManager/manager/dtSolutionConfigure/getSolutionAdata"
    headers = {"Referer": f"{system.base_url}/web/solutionConfigure.html?menuId=544"}
    for sol_type in ['SOLUTION_TYPE_B', 'SOLUTION_TYPE_C', 'SOLUTION_TYPE_D', 'SOLUTION_TYPE_E']:
        params = {
            "_search": "false",
            "nd": str(int(time.time() * 1000)),
            "pageSize": 30,
            "pageNo": 1,
            "sidx": "",
            "sord": "asc",
            "type": sol_type,
            "solutionCode": solution_code,
            "status": "1",
            "pid": system.current_pid or '',
            "pname": system.current_real_name or '',
            "loginId": system.current_pid or '',
        }
        try:
            resp = system.session.get(url, params=params, headers=headers)
            if resp.status_code == 500:
                continue
            resp.raise_for_status()
            data = resp.json()
            items = data.get('resultData', {}).get('voList', [])
            for item in items:
                sc = str(item.get('solutionCode', '')).strip()
                if sc == solution_code:
                    lid = item.get('id')
                    co = str(item.get('configureOrder', '')).strip()
                    if lid:
                        _order_to_id_cache[solution_code] = lid
                        _order_to_id_cache[co] = lid
                        return lid, co
        except Exception:
            pass
    return None, None


def _fetch_solution_view(system, solution_id, order_str=None):  # login_html.py:1727
    """Fetch record via viewDtSolutionConfigure — returns complete detailList.
    type parameter must match record type (B/C→SOLUTION_TYPE_E, D→SOLUTION_TYPE_D).
    If order_str is None, tries SOLUTION_TYPE_E first, then SOLUTION_TYPE_D as fallback."""
    url = f"{system.base_url}/detectionManager/manager/dtSolutionConfigure/viewDtSolutionConfigure"
    headers = {"Referer": f"{system.base_url}/web/solutionConfigure.html?menuId=544"}
    view_type = "SOLUTION_TYPE_E"
    if order_str:
        pfx = order_str.split('-')[0].upper()
        type_map = {'D': 'SOLUTION_TYPE_D', 'C': 'SOLUTION_TYPE_C', 'B': 'SOLUTION_TYPE_E', 'E': 'SOLUTION_TYPE_E'}
        view_type = type_map.get(pfx, 'SOLUTION_TYPE_E')
    resp = system.session.get(url, params={"id": solution_id, "type": view_type}, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    result = data.get('resultData') or {}
    if not order_str and view_type != 'SOLUTION_TYPE_D' and not result.get('detailList'):
        resp2 = system.session.get(url, params={"id": solution_id, "type": "SOLUTION_TYPE_D"}, headers=headers)
        resp2.raise_for_status()
        result2 = resp2.json().get('resultData') or {}
        if result2.get('detailList'):
            result = result2
    return result


def _fetch_solution_detail(system, solution_id):  # login_html.py:1790
    """Fetch record via detail API (saveDetailList always null). Fallback only."""
    url = f"{system.base_url}/detectionManager/manager/dtSolutionConfigure/detail"
    headers = {"Referer": f"{system.base_url}/web/solutionConfigure.html?menuId=544"}
    resp = system.session.get(url, params={"id": solution_id}, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data.get('resultData') or {}


def _first_number(s):  # login_html.py:1800
    """提取字符串前导数字部分，保留原始小数位（避免 str(float) 丢尾零）。
    '10.00(mg/L)' → '10.00'；'' 或无前导数字 → ''
    """
    m = re.match(r'^\s*([\d.]+)', str(s))
    return m.group(1) if m else ''


def _trace_export_chain(system, trace_targets, target_date, target_person):  # login_html.py:1808
    """Trace source chain upward (D→C→B→A), find records with same configurator + date.
    trace_targets: list of (lims_id, configure_order) tuples. Use lims_id if available.
    Returns (matched_records, top_ancestor) where matched_records is ordered top→bottom.
    Stops when: parent is A-type, or source concentration unit is % (weighing type).
    Uses viewDtSolutionConfigure API for complete detailList data.
    """
    matched = []
    visiting = set()

    def _fetch_record(lims_id=None, order_str=None):
        resolved = lims_id
        view_order_str = order_str
        if not resolved and order_str:
            if order_str.startswith('CK-'):
                resolved, co = _resolve_by_solution_code(system, order_str)
                if co and co != order_str:
                    view_order_str = co
            else:
                resolved = _resolve_order_to_lims_id(system, order_str)
        # Fallback: use configureOrder number as ID when resolve fails
        if not resolved and order_str and '-' in order_str:
            num_part = order_str.split('-')[1].strip()
            if num_part.isdigit():
                resolved = int(num_part)
        if not resolved:
            return None

        is_solution_code = order_str and order_str.startswith('CK-')

        def _validate(rec):
            if not order_str:
                return True
            if is_solution_code:
                rec_sc = str(rec.get('solutionCode', '')).strip()
                if rec_sc and rec_sc != order_str:
                    return False
            else:
                rec_order = str(rec.get('configureOrder', '')).strip()
                if rec_order and rec_order != order_str:
                    return False
            return True

        try:
            rec = _fetch_solution_view(system, resolved, order_str=view_order_str)
            if rec and rec.get('id') and _validate(rec):
                return rec
        except Exception:
            pass
        try:
            rec = _fetch_solution_detail(system, resolved)
            if rec and rec.get('id') and _validate(rec):
                return rec
        except Exception:
            pass
        return None

    def _has_pct_source_conc(record, parent_order):
        """Check if parent's source concentration in detailList contains %."""
        for dl in (record.get('detailList') or []):
            dl_code = str(dl.get('originalCode', '')).strip()
            dl_no = str(dl.get('originalNo', '')).strip()
            no_first = dl_no.split('\n')[0].strip().split('|')[0].strip() if dl_no else ''
            if dl_code == parent_order or no_first == parent_order:
                conc = str(dl.get('originalConcentration', '') or '').strip()
                return '%' in conc
        return False

    def _trace(lims_id=None, order_str=None, depth=0):
        if depth > 10:
            return None
        key = str(lims_id or order_str)
        if key in visiting:
            return None
        visiting.add(key)

        record = _fetch_record(lims_id, order_str)
        if not record:
            visiting.discard(key)
            return None

        rec_order = str(record.get('configureOrder') or '').strip() or order_str
        rec_person = str(record.get('configuratorName') or record.get('creatorName') or '').strip()
        rec_date = str(record.get('configureDate') or '').strip()[:10]

        # Check same configurator + date (only when filter is specified)
        if target_person and target_date:
            if rec_person != target_person or not rec_date.startswith(target_date):
                visiting.discard(key)
                return record  # stopping point (different person/date)

        prefix = rec_order.split('-')[0].upper() if '-' in rec_order else ''
        original_code = str(record.get('originalCode') or '').strip()
        parent_orders = [oc.strip() for oc in re.split(r'[,，]', original_code) if oc.strip()]

        # Use totalConstantVolume for actual dilution volume (constantVolume = remaining qty)
        total_vol = record.get('totalConstantVolume')
        constant_volume = float(total_vol if total_vol is not None else record.get('constantVolume') or 0)
        rec_conc = str(record.get('concentration') or '').strip()
        rec_parsed = _parse_conc_field(rec_conc)
        rec_conc_val = rec_parsed[0][1] if rec_parsed else 0
        rec_conc_unit = rec_parsed[0][2] if rec_parsed else ''

        # Get detailList for this record
        detail_list = record.get('detailList') or []
        is_d_type = prefix == 'D'
        # 体积优先取 detailList 原始串（保留 10.00 精度）；record 级 totalConstantVolume 是 float，str() 会丢尾零
        constant_volume_raw = ''
        if detail_list:
            constant_volume_raw = str(detail_list[0].get('volume') or '').strip()
        if not constant_volume_raw:
            constant_volume_raw = str(total_vol if total_vol is not None else record.get('constantVolume') or '')

        # Extract parent info from detailList (if available) or from parent record
        parent_name = ''
        parent_conc_val = 0
        parent_conc_unit = ''
        parent_conc_raw = ''
        received_qty = ''
        received_unit = str(record.get('receivedUint') or 'mL').strip()

        if detail_list and not is_d_type:
            # B/C type: use first detailList row for parent info
            dl0 = detail_list[0]
            parent_name = str(dl0.get('originalName', '')).strip()
            p_conc = str(dl0.get('originalConcentration', '') or '').strip()
            parent_conc_raw = p_conc
            pc = _parse_conc_field(p_conc)
            if pc:
                parent_conc_val = pc[0][1]
                parent_conc_unit = pc[0][2]
            received_qty = str(dl0.get('receivedQuantity', '')).strip()
            received_unit = str(dl0.get('receivedUint', '')).strip()
        else:
            # D-type or no detailList: fetch parent record
            if parent_orders:
                po = parent_orders[0]
                try:
                    resolved_id = _resolve_order_to_lims_id(system, po)
                    if resolved_id:
                        parent_rec = _fetch_solution_view(system, resolved_id, order_str=po)
                    else:
                        parent_rec = None
                    if parent_rec:
                        parent_name = str(parent_rec.get('solutionName') or '').strip()
                        p_conc = str(parent_rec.get('concentration') or '').strip()
                        parent_conc_raw = p_conc
                        pc = _parse_conc_field(p_conc)
                        if pc:
                            parent_conc_val = pc[0][1]
                            parent_conc_unit = pc[0][2]
                except Exception:
                    pass

            # Calculate received quantity if not from detailList
            if not received_qty and parent_conc_val > 0 and constant_volume > 0:
                calc_qty = rec_conc_val * constant_volume / parent_conc_val
                received_qty = f"{calc_qty:.4f}" if received_unit == 'g' else f"{calc_qty:.2f}"

        # Stopping conditions
        is_weighing_top = False
        if prefix == 'B' and received_unit == 'g':
            is_weighing_top = True

        matched.append({
            'level': prefix,
            'configure_order': rec_order,
            'solution_name': str(record.get('solutionName') or '').strip(),
            'solution_code': str(record.get('solutionCode') or '').strip(),
            'concentration': rec_conc,
            'constant_volume': _first_number(constant_volume_raw) or str(constant_volume),
            'medium': str(record.get('medium') or '').strip(),
            'configure_date': rec_date,
            'validity_date': str(record.get('validityDate') or '').strip(),
            'controlled_no': str(record.get('controlledNo') or '').strip(),
            'storage_condition': str(record.get('storageCondition') or '').strip(),
            'received_quantity': received_qty,
            'received_unit': received_unit,
            'parent_name': parent_name,
            'parent_concentration': _first_number(parent_conc_raw) or str(parent_conc_val),
            'parent_conc_unit': parent_conc_unit,
            'original_code': original_code,
            'concentration_count': str(record.get('concentrationCount') or '').strip(),
            '_is_weighing_top': is_weighing_top,
            '_detail_list': detail_list,
        })

        if is_weighing_top:
            visiting.discard(key)
            return record

        # Extract parent originalId from detailList (avoids resolve when getSolutionAdata returns 500)
        # Only use originalId when detailList.originalCode directly matches parent_order.
        # When match is through originalNo (e.g., originalCode=A-5728 but originalNo contains B-3327),
        # the originalId refers to the A-type record, NOT the B-type — wrong mapping.
        parent_id_map = {}
        for dl in detail_list:
            dl_code = str(dl.get('originalCode', '')).strip()
            dl_id = dl.get('originalId')
            if dl_id and dl_code:
                parent_id_map.setdefault(dl_code, dl_id)

        # Continue tracing: filter out A-type parents and %-concentration parents
        if original_code:
            for po in parent_orders:
                po_prefix = po.split('-')[0].upper() if '-' in po else ''
                if po_prefix == 'A':
                    continue
                if _has_pct_source_conc(record, po):
                    continue
                pid = parent_id_map.get(po)
                _trace(lims_id=pid, order_str=po, depth=depth + 1)

        visiting.discard(key)
        return None

    for lims_id, order in trace_targets:
        _trace(lims_id=lims_id, order_str=order)

    matched.reverse()

    # Build lookup
    matched_by_order = {}
    for rec in matched:
        order = rec.get('configure_order', '')
        if order:
            matched_by_order[order] = rec

    # Post-process: expand multi-source records using detailList
    for rec in matched:
        if rec.get('_is_weighing_top'):
            continue
        src_code = rec.get('original_code', '')
        sources = [s.strip() for s in re.split(r'[,，]', src_code) if s.strip()]
        if len(sources) > 1:
            rec['source_details'] = []
            rec_conc = str(rec.get('concentration', '')).strip()
            rec_parsed = _parse_conc_field(rec_conc)
            rec_conc_val = rec_parsed[0][1] if rec_parsed else 0
            vol = float(rec.get('constant_volume', 0))
            for src_order in sources:
                src_name = ''
                src_conc_val = 0
                src_conc_unit = ''
                src_qty = ''

                src_matched = matched_by_order.get(src_order)
                if src_matched:
                    src_name = src_matched.get('solution_name', '')
                    sp = _parse_conc_field(src_matched.get('concentration', ''))
                    if sp:
                        src_conc_val = sp[0][1]
                        src_conc_unit = sp[0][2]
                else:
                    sp2 = src_order.split('-')
                    if len(sp2) >= 2:
                        try:
                            src_id = int(sp2[1].strip())
                            src_rec = _fetch_solution_detail(system, src_id)
                            if src_rec:
                                src_name = str(src_rec.get('solutionName') or '').strip()
                                sp3 = _parse_conc_field(str(src_rec.get('concentration') or ''))
                                if sp3:
                                    src_conc_val = sp3[0][1]
                                    src_conc_unit = sp3[0][2]
                        except Exception:
                            pass
                    if not src_name:
                        cc_count = str(rec.get('concentration_count') or '').strip()
                        cc_parts = cc_count.split(';')
                        if len(cc_parts) >= len(sources):
                            idx = sources.index(src_order)
                            if idx < len(cc_parts):
                                cpart = cc_parts[idx].strip()
                                ci = cpart.rfind(':')
                                if ci > 0:
                                    src_name = cpart[:ci].strip()
                                else:
                                    src_name = cpart or src_order

                if not src_name:
                    src_name = src_order
                if src_conc_val > 0 and vol > 0:
                    calc = rec_conc_val * vol / src_conc_val
                    src_qty = '' if calc > vol else f"{calc:.2f}"
                rec['source_details'].append({
                    'name': src_name,
                    'conc': src_conc_val,
                    'conc_unit': src_conc_unit,
                    'qty': src_qty,
                })

    # Determine top ancestor
    top_ancestor = {}
    if matched:
        top_names = []
        top_codes = []
        for rec in matched:
            if rec.get('_is_weighing_top'):
                name = rec.get('solution_name', '')
            else:
                name = rec.get('parent_name', '')
            if name and name not in top_names:
                top_names.append(name)
            sc = rec.get('solution_code', '')
            sc_parts = sc.split('-')
            bc = '-'.join(sc_parts[:-2]) if len(sc_parts) >= 3 else sc
            if bc and bc not in top_codes:
                top_codes.append(bc)

        if len(top_names) > 1 or len(top_codes) > 1:
            top_ancestor = {
                'solution_name': '；\n'.join(top_names) + '；',
                'controlled_no': '；\n'.join(top_codes) + '；',
                'concentration': '见下表',
            }
        else:
            rec0 = matched[0]
            if rec0.get('_is_weighing_top'):
                top_ancestor = {
                    'solution_name': top_names[0] if top_names else rec0.get('solution_name', ''),
                    'controlled_no': top_codes[0] if top_codes else '',
                    'concentration': rec0.get('concentration', ''),
                }
            else:
                pn = rec0.get('parent_name', '')
                pc = rec0.get('parent_concentration', '')
                pu = rec0.get('parent_conc_unit', '')
                top_ancestor = {
                    'solution_name': pn or rec0.get('solution_name', ''),
                    'controlled_no': top_codes[0] if top_codes else '',
                    'concentration': f"{pc}({pu})" if pc and pu else str(pc) if pc else '',
                }

    return matched, top_ancestor


# ===== 高层封装（mup 专用） =====

def trace_working_solution(code, system):
    """工作液编号(如 'D-9203') → 溯源链记录列表(自上而下 A..B..C..D，top→bottom)。

    system: 已登录对象(`lims_auto_login.LoginResult` 或鸭子兼容:
        .session / .base_url / .current_pid / .current_real_name)。
    target_date/target_person 传空 → 关闭同人同日过滤，全链溯源(与上游 _trace_to_a 一致)。

    返回 matched_records(list[dict])；每条字段: level(A/B/C/D)/configure_order/solution_name/
    solution_code/concentration/constant_volume/medium/configure_date/validity_date/controlled_no/
    received_quantity/received_unit/parent_name/parent_concentration/_is_weighing_top/...
    解析不到编号或溯源链空 → 抛 ValueError(中文信息)。
    """
    code = (code or "").strip()
    if not code:
        raise ValueError("工作液编号为空。")
    lims_id = _resolve_order_to_lims_id(system, code)
    if not lims_id:
        raise ValueError(f"LIMS 未找到工作液编号「{code}」（仅支持 B/C/D/E 型；A 型标准品不可查）。")
    matched, _top = _trace_export_chain(system, [(lims_id, code)], "", "")
    if not matched:
        raise ValueError(f"工作液「{code}」溯源链为空。")
    return matched

/* 픽보조 관리 대시보드 — 프론트엔드 */

let computers = [];
let selectedPC = null;
let eventSource = null;

// ── API 헬퍼 ──────────────────────────────────────────────────────────

async function api(method, path, body) {
    const opts = { method, credentials: "same-origin" };
    if (body) {
        opts.headers = { "Content-Type": "application/json" };
        opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    if (res.status === 401) {
        document.getElementById("app").style.display = "none";
        document.getElementById("loginWrap").style.display = "flex";
        throw new Error("Unauthorized");
    }
    return res.json();
}

// ── 로그인 / 로그아웃 ─────────────────────────────────────────────────

async function doLogin() {
    const pw = document.getElementById("loginPw").value;
    try {
        await api("POST", "/api/auth/login", { password: pw });
        document.getElementById("loginWrap").style.display = "none";
        document.getElementById("app").style.display = "block";
        loadComputers();
        startSSE();
    } catch {
        document.getElementById("loginErr").textContent = "비밀번호가 틀립니다";
    }
}

async function doLogout() {
    await api("POST", "/api/auth/logout");
    if (eventSource) eventSource.close();
    document.getElementById("app").style.display = "none";
    document.getElementById("loginWrap").style.display = "flex";
}

document.getElementById("loginPw").addEventListener("keydown", e => {
    if (e.key === "Enter") doLogin();
});

// ── SSE ───────────────────────────────────────────────────────────────

function startSSE() {
    if (eventSource) eventSource.close();
    eventSource = new EventSource("/api/events");
    eventSource.addEventListener("status", e => {
        const data = JSON.parse(e.data);
        updateStatusFromSSE(data);
    });
    eventSource.onerror = () => {
        setTimeout(startSSE, 5000);
    };
}

function updateStatusFromSSE(statuses) {
    for (const s of statuses) {
        const c = computers.find(c => c.id === s.computer_id);
        if (c) Object.assign(c, s);
    }
    renderSidebar();
    if (!selectedPC) renderOverview();
}

// ── PC 목록 ───────────────────────────────────────────────────────────

async function loadComputers() {
    computers = await api("GET", "/api/computers");
    renderSidebar();
    renderOverview();
}

function renderSidebar() {
    const ul = document.getElementById("pcList");
    ul.innerHTML = computers.map(c => `
        <li class="pc-item ${selectedPC === c.id ? 'active' : ''}"
            onclick="selectPC('${c.id}')">
            <span class="pc-dot ${c.is_online ? 'online' : ''}"></span>
            <span class="pc-name">${c.display_name || c.id}</span>
            <span class="pc-count">${c.enabled_account_count || 0}계정</span>
        </li>
    `).join("");
}

function renderOverview() {
    selectedPC = null;
    document.getElementById("detailPage").classList.add("hidden");
    const div = document.getElementById("overviewPage");
    div.classList.remove("hidden");

    const cards = computers.map(c => `
        <div class="overview-card" onclick="selectPC('${c.id}')" style="cursor:pointer">
            <div class="card-header">
                <span class="card-title">
                    ${c.display_name || c.id}
                    <span class="badge ${c.is_online ? 'online' : 'offline'}">
                        ${c.is_online ? '온라인' : '오프라인'}
                    </span>
                    ${c.monitoring_active ? '<span class="badge monitoring">모니터링</span>' : ''}
                </span>
            </div>
            <div class="stat-row"><span>계정</span><span class="val">${c.enabled_account_count || 0} / ${c.account_count || 0}</span></div>
            <div class="stat-row"><span>성공 / 실패</span><span class="val"><span class="text-ok">${c.success_count || 0}</span> / <span class="text-err">${c.fail_count || 0}</span></span></div>
            <div class="stat-row"><span>최근 코드</span><span class="val">${c.last_code || '-'}</span></div>
            <div class="stat-row"><span>버전</span><span class="val">${c.app_version || '-'}</span></div>
        </div>
    `).join("");

    div.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
            <h2 style="font-size:16px">전체 현황 (${computers.length}대)</h2>
            <button class="btn btn-warn" onclick="showDistribute()">계정 분배</button>
        </div>
        <div class="overview-grid">${cards || '<p class="text-dim">등록된 PC가 없습니다. + 추가 버튼을 눌러주세요.</p>'}</div>
    `;
}

// ── PC 상세 ───────────────────────────────────────────────────────────

async function selectPC(id) {
    selectedPC = id;
    renderSidebar();

    const data = await api("GET", `/api/computers/${id}`);
    const logs = await api("GET", `/api/computers/${id}/logs`);

    document.getElementById("overviewPage").classList.add("hidden");
    const div = document.getElementById("detailPage");
    div.classList.remove("hidden");

    const cfg = data.config || {};
    const bcfg = data.bonus_config || {};
    const accounts = cfg.accounts || [];
    const bonusAccounts = bcfg.accounts || [];
    const proxies = cfg.proxies || [];
    const schedules = cfg.monitor_schedules || [{}, {}];
    const bSchedules = bcfg.schedule_times || ["", "", "", ""];
    const bEnabled = bcfg.schedule_enabled || [false, false, false, false];
    const siteUrls = cfg.site_urls || Array(10).fill("");

    div.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
            <h2 style="font-size:16px">${data.display_name || data.id}
                <span class="badge ${data.is_online ? 'online' : 'offline'}">${data.is_online ? '온라인' : '오프라인'}</span>
            </h2>
            <div class="btn-group" style="margin:0">
                <button class="btn btn-secondary" onclick="renderOverview()">← 목록</button>
                <button class="btn btn-danger" onclick="deletePC('${id}')">PC 삭제</button>
            </div>
        </div>

        <!-- 상태 + 제어 -->
        <div class="detail-section">
            <h3>상태 / 원격 제어</h3>
            <div class="stat-row"><span>모니터링</span><span class="val">${data.status.monitoring_active ? '실행 중' : '대기'}</span></div>
            <div class="stat-row"><span>자동입력</span><span class="val">${data.status.auto_input_active ? '실행 중' : '대기'}</span></div>
            <div class="stat-row"><span>성공 / 실패</span><span class="val"><span class="text-ok">${data.status.success_count}</span> / <span class="text-err">${data.status.fail_count}</span></span></div>
            <div class="stat-row"><span>최근 코드</span><span class="val">${data.status.last_code || '-'}</span></div>
            <div class="stat-row"><span>버전</span><span class="val">${data.status.app_version || '-'}</span></div>
            <div class="stat-row"><span>API 키</span><span class="val" style="font-family:Consolas;font-size:11px">${data.api_key}</span></div>
            <div class="btn-group">
                <button class="btn btn-primary" onclick="sendCmd('${id}','start_monitor')">▶ 모니터링 시작</button>
                <button class="btn btn-danger" onclick="sendCmd('${id}','stop_monitor')">■ 중지</button>
                <input id="manualCode" placeholder="코드 수동 입력" style="padding:6px 10px;background:var(--surface2);border:1px solid var(--border);border-radius:4px;color:var(--fg);font-size:13px;width:140px">
                <button class="btn btn-warn" onclick="sendCode('${id}')">전송</button>
            </div>
        </div>

        <!-- 기본 설정 -->
        <div class="detail-section">
            <h3>기본 설정</h3>
            <div class="form-grid">
                <label>표시 이름</label>
                <input id="cfgDisplayName" value="${data.display_name || ''}">
                <label>채팅방 이름</label>
                <input id="cfgRoomName" value="${cfg.room_name || ''}">
                <label>폴링 간격 (초)</label>
                <input id="cfgPollInterval" type="number" step="0.5" value="${cfg.poll_interval || 3}">
                <label>발신자 필터</label>
                <input id="cfgWatchSender" value="${cfg.watch_sender || ''}">
                <label>워커 수</label>
                <input id="cfgWorkers" type="number" min="1" max="30" value="${cfg.workers || 2}">
                <label>Chrome 포트</label>
                <input id="cfgChromePort" type="number" value="${cfg.chrome_port || 9222}">
                <label>자동입력</label>
                <select id="cfgAutoInput">
                    <option value="true" ${cfg.auto_input ? 'selected' : ''}>ON</option>
                    <option value="false" ${!cfg.auto_input ? 'selected' : ''}>OFF</option>
                </select>
            </div>
        </div>

        <!-- 스케줄 -->
        <div class="detail-section">
            <h3>고정픽 스케줄</h3>
            <div class="form-grid">
                <label>스케줄 1</label>
                <div style="display:flex;gap:8px;align-items:center">
                    <input type="checkbox" id="cfgSched0En" ${schedules[0]?.enabled ? 'checked' : ''}>
                    <input id="cfgSched0Start" value="${schedules[0]?.start || ''}" placeholder="시작" style="width:70px">
                    <span>~</span>
                    <input id="cfgSched0Stop" value="${schedules[0]?.stop || ''}" placeholder="종료" style="width:70px">
                </div>
                <label>스케줄 2</label>
                <div style="display:flex;gap:8px;align-items:center">
                    <input type="checkbox" id="cfgSched1En" ${schedules[1]?.enabled ? 'checked' : ''}>
                    <input id="cfgSched1Start" value="${schedules[1]?.start || ''}" placeholder="시작" style="width:70px">
                    <span>~</span>
                    <input id="cfgSched1Stop" value="${schedules[1]?.stop || ''}" placeholder="종료" style="width:70px">
                </div>
            </div>
            <h3 class="mt-12">보너스픽 스케줄</h3>
            <div class="form-grid">
                ${[0,1,2,3].map(i => `
                    <label>시간 ${i+1}</label>
                    <div style="display:flex;gap:8px;align-items:center">
                        <input type="checkbox" id="cfgBSched${i}En" ${bEnabled[i] ? 'checked' : ''}>
                        <input id="cfgBSched${i}Time" value="${bSchedules[i] || ''}" placeholder="HH:MM" style="width:70px">
                    </div>
                `).join("")}
            </div>
        </div>

        <!-- 사이트 URL -->
        <div class="detail-section">
            <h3>사이트 주소</h3>
            ${siteUrls.map((u, i) => `
                <div style="display:flex;gap:4px;margin-bottom:4px;align-items:center">
                    <input id="cfgUrl${i}" value="${u}" placeholder="사이트 ${i+1}" style="flex:1;padding:6px 10px;background:var(--surface2);border:1px solid var(--border);border-radius:4px;color:var(--fg);font-size:12px;font-family:Consolas">
                    <button class="btn btn-secondary" style="padding:4px 8px;font-size:11px;white-space:nowrap" onclick="testSiteUrl(${i})">테스트</button>
                    <span id="urlStatus${i}" style="font-size:11px;min-width:20px"></span>
                </div>
            `).join("")}
            <button class="btn btn-secondary mt-8" onclick="testAllSiteUrls()">전체 접속 테스트</button>
        </div>

        <!-- 계정 -->
        <div class="detail-section">
            <h3>계정 관리 (${accounts.length}개)</h3>
            <table class="acct-table">
                <thead><tr><th>☑</th><th>#</th><th>이메일</th><th>비밀번호</th><th>메모</th><th>프록시</th><th></th></tr></thead>
                <tbody id="acctBody">
                    ${accounts.map((a, i) => `
                        <tr data-idx="${i}">
                            <td><input type="checkbox" class="acct-en" ${a.enabled !== false ? 'checked' : ''}></td>
                            <td>${i+1}</td>
                            <td><input class="acct-email" value="${a.email || ''}"></td>
                            <td><input class="acct-pw" type="password" value="${a.password || ''}"></td>
                            <td><input class="acct-memo" value="${a.memo || ''}"></td>
                            <td><input class="acct-proxy" value="${a.proxy || ''}" style="font-size:11px"></td>
                            <td><button class="btn btn-danger" style="padding:2px 8px;font-size:11px" onclick="removeAcct(${i})">✕</button></td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
            <div class="btn-group">
                <button class="btn btn-secondary" onclick="addAcctRow()">+ 계정 추가</button>
                <button class="btn btn-danger" onclick="clearAccts('acct')">전체 삭제</button>
                <button class="btn btn-secondary" onclick="importExcel('acct')">엑셀 불러오기</button>
                <button class="btn btn-secondary" onclick="exportExcel('acct')">엑셀 내려받기</button>
                <input type="file" id="excelFileAcct" accept=".xlsx,.xls,.csv" style="display:none" onchange="handleExcelFile(event,'acct')">
            </div>
        </div>

        <!-- 보너스픽 계정 -->
        <div class="detail-section">
            <h3>보너스픽 계정 관리 (${bonusAccounts.length}개)</h3>
            <table class="acct-table">
                <thead><tr><th>☑</th><th>#</th><th>이메일</th><th>비밀번호</th><th>메모</th><th>프록시</th><th></th></tr></thead>
                <tbody id="bonusAcctBody">
                    ${bonusAccounts.map((a, i) => `
                        <tr data-idx="${i}">
                            <td><input type="checkbox" class="bacct-en" ${a.enabled !== false ? 'checked' : ''}></td>
                            <td>${i+1}</td>
                            <td><input class="bacct-email" value="${a.email || ''}"></td>
                            <td><input class="bacct-pw" type="password" value="${a.password || ''}"></td>
                            <td><input class="bacct-memo" value="${a.memo || ''}"></td>
                            <td><input class="bacct-proxy" value="${a.proxy || ''}" style="font-size:11px"></td>
                            <td><button class="btn btn-danger" style="padding:2px 8px;font-size:11px" onclick="removeBonusAcct(${i})">✕</button></td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
            <div class="btn-group">
                <button class="btn btn-secondary" onclick="addBonusAcctRow()">+ 보너스픽 계정 추가</button>
                <button class="btn btn-danger" onclick="clearAccts('bacct')">전체 삭제</button>
                <button class="btn btn-secondary" onclick="importExcel('bacct')">엑셀 불러오기</button>
                <button class="btn btn-secondary" onclick="exportExcel('bacct')">엑셀 내려받기</button>
                <input type="file" id="excelFileBacct" accept=".xlsx,.xls,.csv" style="display:none" onchange="handleExcelFile(event,'bacct')">
            </div>
        </div>

        <!-- 프록시 -->
        <div class="detail-section">
            <h3>프록시 IP (${proxies.length}개)</h3>
            <textarea id="cfgProxies" rows="5">${proxies.join("\\n")}</textarea>
        </div>

        <!-- 저장 -->
        <div class="btn-group" style="justify-content:flex-end;margin-bottom:40px">
            <button class="btn btn-primary" onclick="saveConfig('${id}')" style="padding:10px 32px;font-size:14px">설정 저장</button>
        </div>

        <!-- 로그 -->
        <div class="detail-section">
            <h3>코드 제출 로그</h3>
            <table class="log-table">
                <thead><tr><th>시간</th><th>코드</th><th>전체</th><th>성공</th><th>실패</th></tr></thead>
                <tbody>
                    ${logs.map(l => `
                        <tr>
                            <td>${new Date(l.detected_at).toLocaleString('ko-KR')}</td>
                            <td style="font-family:Consolas">${l.code}</td>
                            <td>${l.total_accounts}</td>
                            <td class="text-ok">${l.success_count}</td>
                            <td class="text-err">${l.fail_count}</td>
                        </tr>
                    `).join("") || '<tr><td colspan="5" class="text-dim">로그 없음</td></tr>'}
                </tbody>
            </table>
        </div>
    `;
}

// ── 설정 저장 ─────────────────────────────────────────────────────────

async function saveConfig(id) {
    const accounts = [];
    document.querySelectorAll("#acctBody tr").forEach(tr => {
        accounts.push({
            email: tr.querySelector(".acct-email").value,
            password: tr.querySelector(".acct-pw").value,
            memo: tr.querySelector(".acct-memo").value,
            proxy: tr.querySelector(".acct-proxy").value,
            enabled: tr.querySelector(".acct-en").checked,
        });
    });

    const siteUrls = [];
    for (let i = 0; i < 10; i++) {
        const el = document.getElementById(`cfgUrl${i}`);
        siteUrls.push(el ? el.value : "");
    }

    const proxies = document.getElementById("cfgProxies").value
        .split("\n").map(s => s.trim()).filter(Boolean);

    const config = {
        room_name: document.getElementById("cfgRoomName").value,
        poll_interval: parseFloat(document.getElementById("cfgPollInterval").value) || 3,
        watch_sender: document.getElementById("cfgWatchSender").value,
        auto_input: document.getElementById("cfgAutoInput").value === "true",
        chrome_port: parseInt(document.getElementById("cfgChromePort").value) || 9222,
        workers: parseInt(document.getElementById("cfgWorkers").value) || 2,
        site_urls: siteUrls,
        accounts: accounts,
        account_index: 0,
        proxies: proxies,
        monitor_schedules: [
            {
                enabled: document.getElementById("cfgSched0En").checked,
                start: document.getElementById("cfgSched0Start").value,
                stop: document.getElementById("cfgSched0Stop").value,
            },
            {
                enabled: document.getElementById("cfgSched1En").checked,
                start: document.getElementById("cfgSched1Start").value,
                stop: document.getElementById("cfgSched1Stop").value,
            },
        ],
    };

    const bonusAccounts = [];
    document.querySelectorAll("#bonusAcctBody tr").forEach(tr => {
        bonusAccounts.push({
            email: tr.querySelector(".bacct-email").value,
            password: tr.querySelector(".bacct-pw").value,
            memo: tr.querySelector(".bacct-memo").value,
            proxy: tr.querySelector(".bacct-proxy").value,
            enabled: tr.querySelector(".bacct-en").checked,
        });
    });

    const bonusConfig = {
        site_urls: siteUrls,
        chrome_port: parseInt(document.getElementById("cfgChromePort").value) || 9222,
        accounts: bonusAccounts,
        account_index: 0,
        schedule_times: [0,1,2,3].map(i => document.getElementById(`cfgBSched${i}Time`).value),
        schedule_enabled: [0,1,2,3].map(i => document.getElementById(`cfgBSched${i}En`).checked),
    };

    const displayName = document.getElementById("cfgDisplayName").value;

    await api("PUT", `/api/computers/${id}/config`, {
        config, bonus_config: bonusConfig, display_name: displayName,
    });

    alert("저장 완료");
    loadComputers();
}

// ── 계정 행 추가/삭제 ─────────────────────────────────────────────────

function addAcctRow() {
    const tbody = document.getElementById("acctBody");
    const idx = tbody.children.length;
    const tr = document.createElement("tr");
    tr.dataset.idx = idx;
    tr.innerHTML = `
        <td><input type="checkbox" class="acct-en" checked></td>
        <td>${idx + 1}</td>
        <td><input class="acct-email" value=""></td>
        <td><input class="acct-pw" type="password" value=""></td>
        <td><input class="acct-memo" value=""></td>
        <td><input class="acct-proxy" value="" style="font-size:11px"></td>
        <td><button class="btn btn-danger" style="padding:2px 8px;font-size:11px" onclick="this.closest('tr').remove()">✕</button></td>
    `;
    tbody.appendChild(tr);
}

function removeAcct(idx) {
    const rows = document.querySelectorAll("#acctBody tr");
    if (rows[idx]) rows[idx].remove();
}

function addBonusAcctRow() {
    const tbody = document.getElementById("bonusAcctBody");
    const idx = tbody.children.length;
    const tr = document.createElement("tr");
    tr.dataset.idx = idx;
    tr.innerHTML = `
        <td><input type="checkbox" class="bacct-en" checked></td>
        <td>${idx + 1}</td>
        <td><input class="bacct-email" value=""></td>
        <td><input class="bacct-pw" type="password" value=""></td>
        <td><input class="bacct-memo" value=""></td>
        <td><input class="bacct-proxy" value="" style="font-size:11px"></td>
        <td><button class="btn btn-danger" style="padding:2px 8px;font-size:11px" onclick="this.closest('tr').remove()">✕</button></td>
    `;
    tbody.appendChild(tr);
}

function removeBonusAcct(idx) {
    const rows = document.querySelectorAll("#bonusAcctBody tr");
    if (rows[idx]) rows[idx].remove();
}

// ── 사이트 접속 테스트 ────────────────────────────────────────────────

async function testSiteUrl(idx) {
    const url = document.getElementById(`cfgUrl${idx}`).value.trim();
    const status = document.getElementById(`urlStatus${idx}`);
    if (!url) { status.textContent = ''; return; }
    status.textContent = '...';
    status.style.color = 'var(--fg-dim)';
    try {
        const res = await fetch(url, { mode: 'no-cors', cache: 'no-store' });
        status.textContent = '✓';
        status.style.color = 'var(--ok)';
    } catch {
        status.textContent = '✕';
        status.style.color = 'var(--error)';
    }
}

async function testAllSiteUrls() {
    for (let i = 0; i < 10; i++) {
        const url = document.getElementById(`cfgUrl${i}`);
        if (url && url.value.trim()) await testSiteUrl(i);
    }
}

function clearAccts(type) {
    if (!confirm("전체 삭제하시겠습니까?")) return;
    const tbody = document.getElementById(type === 'acct' ? 'acctBody' : 'bonusAcctBody');
    tbody.innerHTML = '';
}

// ── 엑셀 불러오기/내려받기 ────────────────────────────────────────────

function importExcel(type) {
    const id = type === 'acct' ? 'excelFileAcct' : 'excelFileBacct';
    document.getElementById(id).click();
}

function handleExcelFile(event, type) {
    const file = event.target.files[0];
    if (!file) return;
    const tbody = document.getElementById(type === 'acct' ? 'acctBody' : 'bonusAcctBody');
    const cls = type === 'acct' ? 'acct' : 'bacct';

    const reader = new FileReader();
    reader.onload = function(e) {
        let rows = [];
        const isExcel = file.name.match(/\.xlsx?$/i);

        if (isExcel && typeof XLSX !== 'undefined') {
            // xlsx/xls 파일
            const data = new Uint8Array(e.target.result);
            const wb = XLSX.read(data, { type: 'array' });
            const ws = wb.Sheets[wb.SheetNames[0]];
            rows = XLSX.utils.sheet_to_json(ws, { header: 1 });
        } else {
            // CSV 파일
            const text = e.target.result;
            rows = text.split("\n").map(l => l.trim()).filter(Boolean).map(l => l.split(",").map(s => s.trim()));
        }

        if (rows.length === 0) { alert("데이터 없음"); return; }

        // 덮어쓰기 / 이어쓰기 선택
        if (tbody.children.length > 0) {
            const overwrite = confirm("기존 계정을 덮어쓸까요?\n\n확인 = 덮어쓰기\n취소 = 이어쓰기");
            if (overwrite) tbody.innerHTML = '';
        }

        for (let i = 0; i < rows.length; i++) {
            const row = rows[i];
            // 헤더 스킵
            if (i === 0) {
                const first = String(row[0] || '').toLowerCase();
                if (first.includes('email') || first.includes('이메일') || first.includes('메일')) continue;
            }
            if (!row[0] || !row[1]) continue;
            const email = String(row[0] || '').trim();
            const password = String(row[1] || '').trim();
            const memo = String(row[2] || '').trim();
            const proxy = String(row[3] || '').trim();
            const idx = tbody.children.length;
            const tr = document.createElement("tr");
            tr.dataset.idx = idx;
            tr.innerHTML = `
                <td><input type="checkbox" class="${cls}-en" checked></td>
                <td>${idx + 1}</td>
                <td><input class="${cls}-email" value="${email}"></td>
                <td><input class="${cls}-pw" type="password" value="${password}"></td>
                <td><input class="${cls}-memo" value="${memo}"></td>
                <td><input class="${cls}-proxy" value="${proxy}" style="font-size:11px"></td>
                <td><button class="btn btn-danger" style="padding:2px 8px;font-size:11px" onclick="this.closest('tr').remove()">✕</button></td>
            `;
            tbody.appendChild(tr);
        }
        alert(`${tbody.children.length}개 계정 로드 완료`);
    };

    if (file.name.match(/\.xlsx?$/i)) {
        reader.readAsArrayBuffer(file);
    } else {
        reader.readAsText(file, 'UTF-8');
    }
    event.target.value = '';
}

function exportExcel(type) {
    const tbody = document.getElementById(type === 'acct' ? 'acctBody' : 'bonusAcctBody');
    const cls = type === 'acct' ? 'acct' : 'bacct';
    let csv = "이메일,비밀번호,메모,프록시,활성화\n";
    tbody.querySelectorAll("tr").forEach(tr => {
        const email = tr.querySelector(`.${cls}-email`).value;
        const pw = tr.querySelector(`.${cls}-pw`).value;
        const memo = tr.querySelector(`.${cls}-memo`).value;
        const proxy = tr.querySelector(`.${cls}-proxy`).value;
        const enabled = tr.querySelector(`.${cls}-en`).checked;
        csv += `${email},${pw},${memo},${proxy},${enabled}\n`;
    });
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = type === 'acct' ? "고정픽_계정.csv" : "보너스픽_계정.csv";
    a.click();
    URL.revokeObjectURL(url);
}

// ── 명령 전송 ─────────────────────────────────────────────────────────

async function sendCmd(id, type) {
    await api("POST", `/api/computers/${id}/command`, { command_type: type });
    alert(`${type} 명령 전송 완료`);
}

async function sendCode(id) {
    const code = document.getElementById("manualCode").value.trim();
    if (!code) return alert("코드를 입력하세요");
    await api("POST", `/api/computers/${id}/command`, {
        command_type: "submit_code",
        payload: { code },
    });
    alert(`코드 ${code} 전송 완료`);
}

// ── PC 추가/삭제 ──────────────────────────────────────────────────────

function showAddPC() {
    document.getElementById("addPCModal").classList.add("show");
    document.getElementById("newPCId").value = "";
    document.getElementById("newPCName").value = "";
    document.getElementById("addPCResult").textContent = "";
}

async function addPC() {
    const id = document.getElementById("newPCId").value.trim();
    if (!id) return;
    try {
        const res = await api("POST", "/api/computers", {
            id, display_name: document.getElementById("newPCName").value.trim(),
        });
        document.getElementById("addPCResult").innerHTML =
            `추가 완료! API 키: <code>${res.api_key}</code><br>이 키를 에이전트 설정에 입력하세요.`;
        loadComputers();
    } catch (e) {
        document.getElementById("addPCResult").textContent = "추가 실패: " + e.message;
    }
}

async function deletePC(id) {
    if (!confirm(`${id}를 삭제하시겠습니까?`)) return;
    await api("DELETE", `/api/computers/${id}`);
    loadComputers();
    renderOverview();
}

function closeModal(id) {
    document.getElementById(id).classList.remove("show");
}

// ── 계정 분배 ─────────────────────────────────────────────────────────

function showDistribute() {
    document.getElementById("distModal").classList.add("show");
    document.getElementById("distAccounts").value = "";
    document.getElementById("distResult").textContent = "";
}

async function distributeAccounts() {
    const text = document.getElementById("distAccounts").value.trim();
    let accounts;
    try {
        accounts = JSON.parse(text);
    } catch {
        document.getElementById("distResult").textContent = "JSON 형식이 올바르지 않습니다";
        return;
    }
    const onlineIds = computers.filter(c => c.is_online).map(c => c.id);
    if (onlineIds.length === 0) {
        document.getElementById("distResult").textContent = "온라인 PC가 없습니다";
        return;
    }
    const res = await api("POST", "/api/computers/distribute-accounts", {
        accounts, computer_ids: onlineIds, strategy: "even",
    });
    const lines = Object.entries(res.distribution).map(([k, v]) => `${k}: ${v}개`).join(", ");
    document.getElementById("distResult").textContent = `분배 완료: ${lines}`;
    loadComputers();
}

// ── 초기화 ────────────────────────────────────────────────────────────

(async function init() {
    try {
        await api("GET", "/api/computers");
        document.getElementById("loginWrap").style.display = "none";
        document.getElementById("app").style.display = "block";
        loadComputers();
        startSSE();
    } catch {
        // 로그인 필요
    }
})();

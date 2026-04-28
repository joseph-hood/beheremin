let nodes = [];
let healthData = {};
let isUpdating = {};
let healthFetchInProgress = false;

const tbody = document.getElementById('nodes-tbody');

async function fetchInfo() {
    try {
        const response = await fetch('/api/info');
        const data = await response.json();
        document.getElementById('hub-ssid').textContent = data.wifi_ssid || '—';
        document.getElementById('hub-ip').textContent = data.hub_ip || '—';
    } catch (error) {
        console.error("Failed to fetch hub info:", error);
    }
}

async function fetchNodes() {
    try {
        const response = await fetch('/api/nodes');
        const data = await response.json();
        nodes = data.nodes || [];
        renderTable();
        await fetchHealth();
    } catch (error) {
        console.error("Failed to fetch nodes:", error);
        tbody.innerHTML = `<tr><td colspan="8" class="loading-cell">Failed to load nodes.</td></tr>`;
    }
}

async function fetchHealth() {
    if (healthFetchInProgress) return;
    healthFetchInProgress = true;

    try {
        const response = await fetch('/api/health');
        healthData = await response.json();
    } catch (error) {
        console.error("Failed to fetch health:", error);
    } finally {
        healthFetchInProgress = false;
        renderTable();
    }
}

async function triggerAllOTA() {
    const online = nodes.filter(n => healthData[n.name]?.status === 'online' && !isUpdating[n.name]);
    if (online.length === 0) return;
    await Promise.all(online.map(n => triggerOTA(n.name)));
}

async function triggerOTA(name) {
    if (isUpdating[name]) return;

    isUpdating[name] = true;
    renderTable();

    try {
        const response = await fetch('/api/ota', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ names: [name] })
        });

        const data = await response.json();
        console.log("OTA result:", data);
    } catch (error) {
        console.error("OTA failed:", error);
        alert(`OTA Update failed for ${name}: ` + error.message);
    } finally {
        isUpdating[name] = false;
        renderTable();
    }
}

function formatUptime(seconds) {
    if (!seconds || seconds <= 0) return '0s';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}h ${m}m ${s}s`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

function renderTable() {
    if (nodes.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="loading-cell">No nodes found in registry.</td></tr>`;
        return;
    }

    tbody.innerHTML = '';

    nodes.forEach(node => {
        const tr = document.createElement('tr');

        const h = healthData[node.name] || null;
        const status  = h ? (h.status  || 'offline') : 'offline';
        const message = h ? ((h.message && h.message !== 'ok') ? h.message : '') : '';
        const version = h ? (h.version || '—') : '—';
        const uptime  = h ? (h.uptime  || 0) : 0;
        const pct     = h ? (h.uptime_pct ?? 0.0) : 0.0;
        const ssid    = h ? (h.ssid || null) : null;

        const badgeClass =
            status === 'online'   ? 'status-online'   :
            status === 'updating' ? 'status-updating'  :
            status === 'error'    ? 'status-error'     :
                                    'status-offline';

        const isCurrentlyUpdating = isUpdating[node.name];
        const displayIp = node.ip ? `<code>${node.ip}</code>` : '<em>Not registered</em>';
        const uptimeStr = (status === 'offline' || status === 'error') ? '0s' : formatUptime(uptime);
        const displayUptime = `${uptimeStr} (${pct.toFixed(1)}%)`;

        const displaySsid = ssid ? `<code>${ssid}</code>` : '<span style="color:var(--text-muted)">—</span>';

        tr.innerHTML = `
            <td><strong>${node.name}</strong></td>
            <td>${displayIp}</td>
            <td>${displaySsid}</td>
            <td>
                <span class="status-badge ${badgeClass}">
                    ${status.charAt(0).toUpperCase() + status.slice(1)}
                </span>
            </td>
            <td><code>${version}</code></td>
            <td class="uptime-cell">${displayUptime}</td>
            <td>${message}</td>
            <td>
                <button class="btn btn-update"
                        onclick="triggerOTA('${node.name}')"
                        ${isCurrentlyUpdating || status !== 'online' ? 'disabled' : ''}>
                    ${isCurrentlyUpdating ? '<span class="action-spinner"></span> Updating...' : 'Update'}
                </button>
            </td>
        `;

        tbody.appendChild(tr);
    });
}

document.addEventListener('DOMContentLoaded', async () => {
    fetchInfo();
    await fetchNodes();
    setInterval(fetchHealth, 3000);
});

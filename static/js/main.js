document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("downloadForm");
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");
    const statusBadge = document.getElementById("statusBadge");
    const progressBar = document.getElementById("progressBar");
    const progressPercent = document.getElementById("progressPercent");
    const currentIssueText = document.getElementById("currentIssueText");

    const statTotal = document.getElementById("statTotal");
    const statSuccess = document.getElementById("statSuccess");
    const statSkipped = document.getElementById("statSkipped");
    const statFailed = document.getElementById("statFailed");

    const logConsole = document.getElementById("logConsole");
    const clearLogsBtn = document.getElementById("clearLogsBtn");
    const refreshLibraryBtn = document.getElementById("refreshLibraryBtn");
    const filesTableBody = document.getElementById("filesTableBody");

    let statusInterval = null;

    // Handle Form Submit (Start Download)
    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const data = {
            magazine: document.getElementById("magazine").value,
            email: document.getElementById("email").value,
            password: document.getElementById("password").value,
            start_year: parseInt(document.getElementById("start_year").value),
            start_month: parseInt(document.getElementById("start_month").value),
            end_year: parseInt(document.getElementById("end_year").value),
            end_month: parseInt(document.getElementById("end_month").value),
            download_dir: document.getElementById("download_dir").value,
            headless: document.getElementById("headless").checked
        };

        startBtn.disabled = true;
        stopBtn.disabled = false;

        try {
            const res = await fetch("/api/start-download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data)
            });

            const result = await res.json();
            if (!res.ok || !result.success) {
                alert(result.message || "Fout bij starten van download.");
                startBtn.disabled = false;
                stopBtn.disabled = true;
                return;
            }

            startPollingStatus();
        } catch (err) {
            alert("Verbindingsfout: " + err.message);
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }
    });

    // Handle Stop Download
    stopBtn.addEventListener("click", async () => {
        try {
            await fetch("/api/stop-download", { method: "POST" });
            stopBtn.disabled = true;
        } catch (err) {
            console.error("Fout bij stoppen download:", err);
        }
    });

    // Clear logs
    clearLogsBtn.addEventListener("click", () => {
        logConsole.innerHTML = "";
    });

    // Refresh Downloaded Files Library
    refreshLibraryBtn.addEventListener("click", loadDownloadedFiles);

    function startPollingStatus() {
        if (statusInterval) clearInterval(statusInterval);
        statusInterval = setInterval(pollStatus, 1000);
        pollStatus();
    }

    async function pollStatus() {
        try {
            const res = await fetch("/api/status");
            if (!res.ok) return;
            const data = await res.json();

            const status = data.status || "idle";
            const stats = data.stats || {};

            // Update badge
            statusBadge.className = "badge badge-" + status;
            statusBadge.textContent = status.toUpperCase();

            // Update progress & stats
            const total = stats.total || 0;
            const current = stats.current || 0;
            const pct = total > 0 ? Math.round((current / total) * 100) : 0;

            progressBar.style.width = pct + "%";
            progressPercent.textContent = pct + "%";
            currentIssueText.textContent = stats.current_issue || (status === "running" ? "Verwerken..." : "Gereed");

            statTotal.textContent = total;
            statSuccess.textContent = stats.success || 0;
            statSkipped.textContent = stats.skipped || 0;
            statFailed.textContent = stats.failed || 0;

            // Render logs
            if (data.logs && data.logs.length > 0) {
                logConsole.innerHTML = data.logs.map(log => 
                    `<div class="log-entry"><span class="text-muted">[${log.timestamp}]</span> ${escapeHtml(log.text)}</div>`
                ).join("");
                logConsole.scrollTop = logConsole.scrollHeight;
            }

            // Buttons state management
            if (status === "running") {
                startBtn.disabled = true;
                stopBtn.disabled = false;
            } else {
                startBtn.disabled = false;
                stopBtn.disabled = true;
                if (statusInterval && (status === "completed" || status === "failed" || status === "stopped" || status === "idle")) {
                    clearInterval(statusInterval);
                    statusInterval = null;
                    loadDownloadedFiles();
                }
            }

        } catch (err) {
            console.error("Fout bij status opvragen:", err);
        }
    }

    async function loadDownloadedFiles() {
        try {
            const res = await fetch("/api/downloads");
            if (!res.ok) return;
            const data = await res.json();

            if (!data.files || data.files.length === 0) {
                filesTableBody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">Geen bestanden gevonden in de opslagmap.</td></tr>`;
                return;
            }

            filesTableBody.innerHTML = data.files.map(file => `
                <tr>
                    <td><i class="fa-solid fa-file-pdf text-danger"></i> <strong>${escapeHtml(file.name)}</strong></td>
                    <td>${file.size}</td>
                    <td>${file.mtime}</td>
                    <td>
                        <a href="/download-file/${encodeURIComponent(file.name)}" target="_blank" class="btn btn-sm btn-primary">
                            <i class="fa-solid fa-download"></i> Openen
                        </a>
                    </td>
                </tr>
            `).join("");

        } catch (err) {
            console.error("Fout bij laden van gedownloade bestanden:", err);
        }
    }

    function escapeHtml(str) {
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // Initial loads
    pollStatus();
    loadDownloadedFiles();
});

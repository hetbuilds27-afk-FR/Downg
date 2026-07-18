const BOOT_LINES = [
    "initializing extract.sh v1.0 ...",
    "loading yt-dlp core ... <span class=\"ok\">OK</span>",
    "loading ffmpeg codec ... <span class=\"ok\">OK</span>",
    "standing by for target url_"
];

function playBootLog() {
    const log = document.getElementById("boot-log");
    log.innerHTML = "";

    BOOT_LINES.forEach((text, i) => {
        const el = document.createElement("span");
        el.className = "line";
        el.style.animationDelay = `${i * 140}ms`;
        el.innerHTML = text;
        log.appendChild(el);
        log.appendChild(document.createElement("br"));
    });
}

document.addEventListener("DOMContentLoaded", playBootLog);

async function startDownload() {

    const url =
        document.getElementById("url").value.trim();

    const status =
        document.getElementById("status");

    const progressBar =
        document.getElementById("progress-bar");

    const progressPercent =
        document.getElementById("progress-percent");

    if (!url) {

        status.innerHTML =
            `<span class="error">no target url supplied</span>`;

        return;
    }

    status.innerHTML =
        `<span class="dim">&gt; resolving target</span><span class="cursor-blink"></span>`;

    progressBar.style.width = "0%";
    progressPercent.textContent = "0%";

    // Start download request
    let response;

    try {
        response = await fetch("/download", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                url: url
            })
        });
    } catch (err) {
        status.innerHTML = `<span class="error">connection refused: ${err.message}</span>`;
        return;
    }

    const data = await response.json();

    if (!data.success) {

        status.innerHTML =
            `<span class="error">${data.error}</span>`;

        return;
    }

    const downloadId =
        data.download_id;

    // Start checking progress
    checkProgress(downloadId);
}

function triggerAutoDownload(downloadId) {
    const link = document.createElement("a");
    link.href = `/file/${downloadId}`;
    link.setAttribute("download", "");
    document.body.appendChild(link);
    link.click();
    link.remove();
}

async function checkProgress(downloadId) {

    const status =
        document.getElementById("status");

    const progressBar =
        document.getElementById("progress-bar");

    const progressPercent =
        document.getElementById("progress-percent");

    let autoDownloadFired = false;

    const interval = setInterval(async () => {

        const response =
            await fetch(`/progress/${downloadId}`);

        const data =
            await response.json();

        // Update progress bar
        if (data.progress !== undefined) {

            progressBar.style.width =
                data.progress + "%";

            progressPercent.textContent =
                data.progress + "%";
        }

        const isError = typeof data.status === "string" && data.status.startsWith("Error");
        const isDone = data.status === "Completed";

        // Build status HTML
        let html = "";

        if (data.title) {
            html += `<div class="song-title">${data.title}</div>`;
        }

        if (data.status) {
            const cls = isError ? "error" : "download-status";
            html += `<div class="${cls}">${data.status}</div>`;

            if (!isDone && !isError) {
                html += `<span class="cursor-blink"></span>`;
            }
        }

        status.innerHTML = html;

        if (isDone) {

            clearInterval(interval);

            status.innerHTML = `
                <div class="song-title">${data.title}</div>
                <div class="completed">extraction complete — pulling file to disk</div>
                <a class="download-link" href="/file/${downloadId}">
                    manual download (if auto-save was blocked)
                </a>
            `;

            if (!autoDownloadFired) {
                autoDownloadFired = true;
                triggerAutoDownload(downloadId);
            }
        }

        if (isError) {
            clearInterval(interval);
        }

    }, 1000);
}
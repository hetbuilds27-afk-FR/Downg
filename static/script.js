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

function startMatrixRain() {
    const canvas = document.getElementById("matrix-rain");
    const ctx = canvas.getContext("2d");

    const chars = "アイウエオカキクケコサシスセソ01ABCDEFGHIJKLMNOPQRSTUVWXYZ";

    let columns, drops;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        columns = Math.floor(canvas.width / 16);
        drops = new Array(columns).fill(1);
    }

    resize();
    window.addEventListener("resize", resize);

    function draw() {
        ctx.fillStyle = "rgba(10, 14, 10, 0.08)";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.fillStyle = "#2a7a4a";
        ctx.font = "14px 'JetBrains Mono', monospace";

        for (let i = 0; i < drops.length; i++) {
            const char = chars[Math.floor(Math.random() * chars.length)];
            ctx.fillText(char, i * 16, drops[i] * 16);

            if (drops[i] * 16 > canvas.height && Math.random() > 0.975) {
                drops[i] = 0;
            }
            drops[i]++;
        }
    }

    setInterval(draw, 60);
}

document.addEventListener("DOMContentLoaded", () => {
    playBootLog();
    startMatrixRain();
});

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

function renderPlayer(downloadId) {
    const player = document.createElement("audio");
    player.controls = true;
    player.autoplay = true;
    player.src = `/stream/${downloadId}`;
    player.className = "player";
    return player;
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
                <div class="completed">extraction complete — streaming from server</div>
            `;

            if (!autoDownloadFired) {
                autoDownloadFired = true;
                status.appendChild(renderPlayer(downloadId));
            }
        }

        if (isError) {
            clearInterval(interval);
        }

    }, 1000);
}
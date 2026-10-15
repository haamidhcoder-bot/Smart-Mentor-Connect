/*
 * bg-email-watcher.js
 *
 * Include this once, sitewide, e.g. in base.html right before </body>:
 *
 *   <script src="{{ url_for('static', filename='js/bg-email-watcher.js') }}"></script>
 *
 * When the user clicks "Run in Background" on /loading, that page stores
 * {jobId, sub, exam} under localStorage["bgEmailJob"] and navigates to
 * /home. This script checks for that on every page load, keeps polling
 * /send_results/status/<job_id> in the background, and pops up a small
 * toast when the job finishes (or fails) - no matter which page the user
 * is on at the time.
 */
(function () {
    var STORAGE_KEY = "bgEmailJob";

    function getJob() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    function clearJob() {
        localStorage.removeItem(STORAGE_KEY);
    }

    function showToast(message, isError) {
        var existing = document.getElementById("bg-email-toast");
        if (existing) existing.remove();

        var toast = document.createElement("div");
        toast.id = "bg-email-toast";
        toast.textContent = message;
        toast.title = "Click to dismiss";

        Object.assign(toast.style, {
            position: "fixed",
            bottom: "24px",
            right: "24px",
            maxWidth: "320px",
            padding: "16px 20px",
            borderRadius: "10px",
            boxShadow: "0 4px 16px rgba(0,0,0,0.18)",
            color: "#fff",
            fontSize: "14px",
            lineHeight: "1.4",
            zIndex: "9999",
            background: isError ? "#d9363e" : "#1f6feb",
            cursor: "pointer"
        });

        toast.addEventListener("click", function () {
            toast.remove();
        });

        document.body.appendChild(toast);
        setTimeout(function () {
            if (toast.parentNode) toast.remove();
        }, 8000);
    }

    function poll(job) {
        fetch("/send_results/status/" + job.jobId)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.status === "done") {
                    showToast(
                        "Results sent! " + data.sent_count + " email(s) delivered for " +
                        job.sub + " (" + job.exam + ").",
                        false
                    );
                    clearJob();
                } else if (data.status === "error") {
                    showToast("Sending results failed: " + (data.message || "Unknown error"), true);
                    clearJob();
                } else if (data.status === "cancelled") {
                    clearJob();
                } else {
                    // still running
                    setTimeout(function () { poll(job); }, 2000);
                }
            })
            .catch(function () {
                // network hiccup or job expired - back off and retry a couple times
                // rather than losing the notification entirely
                setTimeout(function () { poll(job); }, 4000);
            });
    }

    document.addEventListener("DOMContentLoaded", function () {
        var job = getJob();
        if (job && job.jobId) {
            poll(job);
        }
    });
})();

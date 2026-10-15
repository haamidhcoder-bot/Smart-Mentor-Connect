/*
    =====================================
    FACE CAPTURE HELPER
    =====================================
    Grabs a still frame from a <video> element for Face ID.

    If the scene looks dark, the whole screen is briefly flashed white
    first (like a phone's screen-flash selfie trick) so the camera has
    something bright to expose against before the photo is taken. This
    keeps registered/login face captures clear enough to compare
    reliably even in dim rooms.
*/

(function () {
    const FLASH_CLASS = "face-capture-flash";
    const DARK_THRESHOLD = 90;   // 0-255 average luminance; below this we flash
    const FLASH_HOLD_MS = 380;   // time for the flash light + auto-exposure to catch up

    function ensureFlashEl() {
        let flash = document.querySelector("." + FLASH_CLASS);
        if (!flash) {
            flash = document.createElement("div");
            flash.className = FLASH_CLASS;
            document.body.appendChild(flash);
        }
        return flash;
    }

    function averageBrightness(video) {
        const sampleCanvas = document.createElement("canvas");
        const w = 40, h = 30;
        sampleCanvas.width = w;
        sampleCanvas.height = h;
        const ctx = sampleCanvas.getContext("2d");
        ctx.drawImage(video, 0, 0, w, h);

        let data;
        try {
            data = ctx.getImageData(0, 0, w, h).data;
        } catch (err) {
            // Canvas may be tainted in rare setups; assume it's bright
            // enough rather than block the capture.
            return 255;
        }

        let total = 0;
        for (let i = 0; i < data.length; i += 4) {
            total += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
        }
        return total / (data.length / 4);
    }

    function wait(ms) {
        return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }

    /**
     * Capture a still frame from `video` onto `canvas`, brightening the
     * scene with a full-screen white flash first if it looks dark.
     * Returns a Promise<Blob> (JPEG).
     */
    window.captureFaceFrame = async function (video, canvas) {
        const brightness = averageBrightness(video);
        const flash = ensureFlashEl();

        if (brightness < DARK_THRESHOLD) {
            flash.classList.add("is-active");
            await wait(FLASH_HOLD_MS);
        }

        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);

        flash.classList.remove("is-active");

        return new Promise(function (resolve) {
            canvas.toBlob(function (blob) { resolve(blob); }, "image/jpeg", 0.92);
        });
    };
})();

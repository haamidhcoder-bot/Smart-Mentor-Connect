document.addEventListener("DOMContentLoaded", function () {

    const overlay = document.getElementById("emailLoadingOverlay");

    if (!overlay) {
        return;
    }

    const forms = document.querySelectorAll(
        'form[data-email-action="send"]'
    );

    forms.forEach(function (form) {

        form.addEventListener("submit", function () {

            // Prevent multiple submissions
            const submitButton = form.querySelector(
                'button[type="submit"], input[type="submit"]'
            );

            if (submitButton) {
                submitButton.disabled = true;

                if (submitButton.tagName === "BUTTON") {
                    submitButton.dataset.originalText =
                        submitButton.innerHTML;

                    submitButton.innerHTML = "Sending...";
                }
            }

            // Show animation
            overlay.classList.add("active");

        });

    });

});
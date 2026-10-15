document.addEventListener("DOMContentLoaded", function () {

    document.querySelectorAll(".password-toggle-btn").forEach(function (btn) {

        btn.addEventListener("click", function () {

            const input = document.getElementById(btn.dataset.target);
            if (!input) {
                return;
            }

            const eyeIcon = btn.querySelector(".icon-eye");
            const eyeOffIcon = btn.querySelector(".icon-eye-off");
            const isHidden = input.type === "password";

            input.type = isHidden ? "text" : "password";

            if (eyeIcon) {
                eyeIcon.style.display = isHidden ? "none" : "block";
            }
            if (eyeOffIcon) {
                eyeOffIcon.style.display = isHidden ? "block" : "none";
            }

            btn.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
        });
    });

});

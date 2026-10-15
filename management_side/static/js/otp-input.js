/* OTP box input — verifies against the real backend via fetch (no page
   reload), then plays the shake (wrong) or checkmark+ripple (correct)
   animation inline, matching the original animation design. */
(function () {
  function setupOtpGroup(group) {
    var form = group.closest('form');
    if (!form) return;

    var inputs = [].slice.call(group.querySelectorAll('.otp-input'));
    var boxes = inputs.map(function (inp) { return inp.parentNode; });
    var hidden = form.querySelector('input[name="onepass"][type="hidden"]');
    var submitBtn = form.querySelector('button[type="submit"]');
    var statusText = form.querySelector('.otp-status-text');
    var statusEl = form.querySelector('.otp-status');
    var N = inputs.length;
    if (!N) return;

    var verifying = false;

    function setStatus(text, state) {
      if (!statusText || !statusEl) return;
      statusText.textContent = text;
      statusEl.className = 'otp-status' + (state ? ' otp-status--' + state : '');
    }

    function syncHidden() {
      if (hidden) hidden.value = inputs.map(function (inp) { return inp.value; }).join('');
    }

    function allFilled() {
      return inputs.every(function (inp) { return inp.value.length === 1; });
    }

    function currentCode() {
      return inputs.map(function (inp) { return inp.value; }).join('');
    }

    function setDisabled(disabled) {
      inputs.forEach(function (inp) { inp.disabled = disabled; });
      if (submitBtn) submitBtn.disabled = disabled || !allFilled();
    }

    function resetBoxes() {
      group.classList.remove('otp-boxes--success', 'otp-boxes--error', 'otp-boxes--verifying');
      inputs.forEach(function (inp, i) {
        inp.value = '';
        boxes[i].classList.remove('otp-box--filled', 'otp-box--active', 'otp-box--tap');
      });
      syncHidden();
    }

    function showSuccess(message) {
      verifying = false;
      group.classList.remove('otp-boxes--error', 'otp-boxes--verifying');
      group.classList.add('otp-boxes--success');
      setDisabled(true);
      setStatus(message || 'Code verified', 'ok');
    }

    function showError(message) {
      verifying = false;
      group.classList.remove('otp-boxes--verifying');
      group.classList.add('otp-boxes--error');
      setStatus(message || 'Incorrect code, try again', 'err');
      setTimeout(function () {
        group.classList.remove('otp-boxes--error');
        resetBoxes();
        setDisabled(false);
        setStatus('Enter the 4-digit code', '');
        try { inputs[0].focus(); } catch (e) {}
      }, 1500);
    }

    function verify() {
      if (verifying || !allFilled()) return;
      verifying = true;
      syncHidden();
      setDisabled(true);
      group.classList.remove('otp-boxes--error', 'otp-boxes--success');
      group.classList.add('otp-boxes--verifying');
      setStatus('Verifying…', '');

      fetch(form.action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ onepass: currentCode() })
      })
        .then(function (res) {
          return res.json().catch(function () { return {}; }).then(function (data) {
            return { ok: res.ok, data: data || {} };
          });
        })
        .then(function (result) {
          if (result.ok && result.data.success) {
            showSuccess(result.data.message);
            var redirectTo = result.data.redirect || '/';
            setTimeout(function () { window.location.href = redirectTo; }, 1600);
          } else {
            showError(result.data.message);
          }
        })
        .catch(function () {
          verifying = false;
          group.classList.remove('otp-boxes--verifying');
          setDisabled(false);
          setStatus('Network error, please try again.', 'err');
        });
    }

    inputs.forEach(function (inp, idx) {
      inp.addEventListener('focus', function () {
        boxes.forEach(function (b) { b.classList.remove('otp-box--active'); });
        boxes[idx].classList.add('otp-box--active');
      });

      inp.addEventListener('input', function () {
        var v = inp.value.replace(/[^0-9]/g, '');
        inp.value = v.slice(-1);
        if (inp.value) {
          boxes[idx].classList.remove('otp-box--tap');
          void boxes[idx].offsetWidth;
          boxes[idx].classList.add('otp-box--filled', 'otp-box--tap');
          if (idx < N - 1) {
            inputs[idx + 1].focus();
            try { inputs[idx + 1].select(); } catch (e) {}
          }
        } else {
          boxes[idx].classList.remove('otp-box--filled');
        }
        group.classList.remove('otp-boxes--error', 'otp-boxes--success');
        syncHidden();
        if (submitBtn) submitBtn.disabled = !allFilled();
        if (allFilled()) verify();
      });

      inp.addEventListener('keydown', function (e) {
        var k = e.key;
        if (k === 'Backspace') {
          if (!inp.value && idx > 0) {
            e.preventDefault();
            inputs[idx - 1].focus();
            inputs[idx - 1].value = '';
            boxes[idx - 1].classList.remove('otp-box--filled');
          } else if (inp.value) {
            inp.value = '';
            boxes[idx].classList.remove('otp-box--filled');
          }
          group.classList.remove('otp-boxes--error', 'otp-boxes--success');
          syncHidden();
          if (submitBtn) submitBtn.disabled = !allFilled();
        } else if (k === 'ArrowLeft' && idx > 0) {
          e.preventDefault();
          inputs[idx - 1].focus();
        } else if (k === 'ArrowRight' && idx < N - 1) {
          e.preventDefault();
          inputs[idx + 1].focus();
        }
      });

      inp.addEventListener('paste', function (e) {
        e.preventDefault();
        var data = e.clipboardData || window.clipboardData;
        var text = data ? data.getData('text') : '';
        var digits = (text || '').replace(/[^0-9]/g, '').slice(0, N).split('');
        if (!digits.length) return;
        group.classList.remove('otp-boxes--error', 'otp-boxes--success');
        digits.forEach(function (d, i) {
          inputs[i].value = d;
          boxes[i].classList.add('otp-box--filled');
        });
        var next = Math.min(digits.length, N - 1);
        inputs[next].focus();
        syncHidden();
        if (submitBtn) submitBtn.disabled = !allFilled();
        if (allFilled()) verify();
      });
    });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      verify();
    });

    if (submitBtn) submitBtn.disabled = true;
    try { inputs[0].focus(); } catch (e) {}
  }

  document.querySelectorAll('[data-otp-group]').forEach(setupOtpGroup);
})();

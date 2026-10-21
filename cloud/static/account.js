'use strict';
for (const button of document.querySelectorAll('[data-action]')) {
  button.addEventListener('click', async () => {
    button.disabled = true;
    const output = document.getElementById('result');
    try {
      const response = await fetch(button.dataset.action, {method: 'POST', headers: {
        'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content,
      }});
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Please sign in again.');
      if (result.redirect === '/login') location.assign('/login');
      else output.textContent = result.message;
    } catch (error) { output.textContent = error.message; }
    finally { button.disabled = false; }
  });
}

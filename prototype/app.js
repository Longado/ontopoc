const steps = document.querySelectorAll('.step');
const panels = document.querySelectorAll('.panel-view');
const toast = document.getElementById('toast');

function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  window.setTimeout(() => toast.classList.remove('show'), 1600);
}

steps.forEach((step) => {
  step.addEventListener('click', () => {
    steps.forEach((item) => item.classList.remove('active'));
    panels.forEach((panel) => panel.classList.add('hidden'));
    step.classList.add('active');
    document.getElementById(step.dataset.panel).classList.remove('hidden');
  });
});

document.querySelectorAll('[data-action="confirm"]').forEach((button) => {
  button.addEventListener('click', () => showToast('原型：关系确认将写入追加式审查记录'));
});

document.querySelectorAll('[data-action="export"]').forEach((button) => {
  button.addEventListener('click', () => showToast('Draft Review Package：包含未决项，不代表 confirmed 交接'));
});

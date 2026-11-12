(() => {
  'use strict';

  const menuButton = document.querySelector('.menu-toggle');
  const nav = document.getElementById('main-nav');
  if (menuButton && nav) {
    menuButton.addEventListener('click', () => {
      const aberto = nav.classList.toggle('nav-open');
      menuButton.classList.toggle('is-open', aberto);
      menuButton.setAttribute('aria-expanded', String(aberto));
    });
    nav.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
      nav.classList.remove('nav-open');
      menuButton.classList.remove('is-open');
      menuButton.setAttribute('aria-expanded', 'false');
    }));
  }

  document.querySelectorAll('.flash').forEach((flash) => {
    const fechar = () => {
      flash.classList.add('flash-hide');
      window.setTimeout(() => flash.remove(), 240);
    };
    flash.querySelector('.flash-close')?.addEventListener('click', fechar);
    if (flash.hasAttribute('data-auto-dismiss')) {
      window.setTimeout(fechar, flash.classList.contains('flash-erro') ? 9000 : 6000);
    }
  });

  document.querySelectorAll('[data-auto-submit]').forEach((campo) => {
    campo.addEventListener('change', () => campo.form?.submit());
  });

  document.querySelectorAll('[data-collapse-target]').forEach((botao) => {
    const alvoId = botao.dataset.collapseTarget;
    const conteudo = alvoId ? document.getElementById(alvoId) : null;
    if (!conteudo) return;

    const rotulo = botao.querySelector('.btn-collapse-label');
    const chave = botao.dataset.storageKey || `controle-notas:collapse:${alvoId}`;

    function aplicarEstado(aberto, salvar = true) {
      conteudo.hidden = !aberto;
      botao.setAttribute('aria-expanded', String(aberto));
      botao.classList.toggle('is-expanded', aberto);
      if (rotulo) rotulo.textContent = aberto ? 'Minimizar calendário' : 'Mostrar calendário';
      if (salvar) {
        try {
          window.localStorage.setItem(chave, aberto ? 'open' : 'closed');
        } catch (_) {
          // O navegador pode bloquear o armazenamento local; o controle continua funcionando.
        }
      }
    }

    let estadoInicial = false;
    try {
      estadoInicial = window.localStorage.getItem(chave) === 'open';
    } catch (_) {
      estadoInicial = false;
    }
    aplicarEstado(estadoInicial, false);

    botao.addEventListener('click', () => {
      aplicarEstado(botao.getAttribute('aria-expanded') !== 'true');
    });
  });

  function formatarDocumento(valor) {
    const digitos = String(valor || '').replace(/\D/g, '').slice(0, 14);
    if (digitos.length <= 11) {
      return digitos
        .replace(/(\d{3})(\d)/, '$1.$2')
        .replace(/(\d{3})(\d)/, '$1.$2')
        .replace(/(\d{3})(\d{1,2})$/, '$1-$2');
    }
    return digitos
      .replace(/(\d{2})(\d)/, '$1.$2')
      .replace(/(\d{3})(\d)/, '$1.$2')
      .replace(/(\d{3})(\d)/, '$1/$2')
      .replace(/(\d{4})(\d{1,2})$/, '$1-$2');
  }

  document.querySelectorAll('[data-document-mask]').forEach((campo) => {
    campo.value = formatarDocumento(campo.value);
    campo.addEventListener('input', () => {
      const inicio = campo.selectionStart;
      const tamanhoAntes = campo.value.length;
      campo.value = formatarDocumento(campo.value);
      const diferenca = campo.value.length - tamanhoAntes;
      const novaPosicao = Math.max(0, (inicio || campo.value.length) + diferenca);
      campo.setSelectionRange(novaPosicao, novaPosicao);
    });
  });

  const codigoEmpresa = document.querySelector('[data-company-code]');
  const previewEmpresa = document.querySelector('[data-company-preview]');
  function atualizarPreviewEmpresa() {
    if (!codigoEmpresa || !previewEmpresa) return;
    const codigo = codigoEmpresa.value.trim();
    const info = (window.companyData || {})[codigo];
    if (info) {
      previewEmpresa.textContent = `${info.name}${info.doc ? ` — ${info.doc}` : ''}`;
      previewEmpresa.classList.remove('preview-error');
    } else if (codigo) {
      previewEmpresa.textContent = 'Código não encontrado ou empresa inativa';
      previewEmpresa.classList.add('preview-error');
    } else {
      previewEmpresa.textContent = '—';
      previewEmpresa.classList.remove('preview-error');
    }
  }
  codigoEmpresa?.addEventListener('input', atualizarPreviewEmpresa);
  atualizarPreviewEmpresa();

  document.querySelectorAll('[data-confirm-duplicate]').forEach((botao) => {
    botao.addEventListener('click', () => {
      const form = document.querySelector(botao.dataset.confirmDuplicate);
      if (!form) return;
      const campo = form.querySelector('input[name="confirmar_duplicado"]');
      if (campo) campo.value = '1';
      form.requestSubmit();
    });
  });

  const modal = document.getElementById('confirm-modal');
  if (!modal) return;
  const modalTitle = document.getElementById('confirm-modal-title');
  const modalMessage = document.getElementById('confirm-modal-message');
  const phraseField = modal.querySelector('.modal-phrase-field');
  const phraseInput = document.getElementById('confirm-modal-phrase');
  const phraseHint = document.getElementById('confirm-modal-hint');
  const confirmButton = modal.querySelector('.modal-confirm');
  const cancelButtons = modal.querySelectorAll('.modal-cancel, .modal-close');
  let pendingForm = null;
  let requiredPhrase = '';

  function closeModal() {
    modal.classList.remove('modal-visible');
    window.setTimeout(() => {
      modal.hidden = true;
      pendingForm = null;
      requiredPhrase = '';
      phraseInput.value = '';
      phraseInput.classList.remove('input-error');
    }, 180);
  }

  function openModal(form) {
    pendingForm = form;
    requiredPhrase = (form.dataset.confirmPhrase || '').trim().toUpperCase();
    modalTitle.textContent = form.dataset.confirmTitle || 'Confirmar ação';
    modalMessage.textContent = form.dataset.confirmMessage || 'Deseja continuar?';
    phraseField.hidden = !requiredPhrase;
    phraseHint.textContent = requiredPhrase ? `Digite ${requiredPhrase} para confirmar.` : '';
    phraseInput.value = '';
    phraseInput.classList.remove('input-error');
    modal.hidden = false;
    window.requestAnimationFrame(() => modal.classList.add('modal-visible'));
    window.setTimeout(() => (requiredPhrase ? phraseInput : confirmButton).focus(), 80);
  }

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.classList.contains('js-confirm')) return;
    if (form.dataset.confirmed === '1') {
      delete form.dataset.confirmed;
      return;
    }
    event.preventDefault();
    openModal(form);
  });

  confirmButton.addEventListener('click', () => {
    if (!pendingForm) return;
    if (requiredPhrase && phraseInput.value.trim().toUpperCase() !== requiredPhrase) {
      phraseInput.classList.add('input-error');
      phraseInput.focus();
      return;
    }
    const hidden = pendingForm.querySelector('input[name="confirmacao"]');
    if (hidden && requiredPhrase) hidden.value = requiredPhrase;
    pendingForm.dataset.confirmed = '1';
    const form = pendingForm;
    closeModal();
    window.setTimeout(() => form.requestSubmit(), 190);
  });

  cancelButtons.forEach((button) => button.addEventListener('click', closeModal));
  modal.addEventListener('click', (event) => {
    if (event.target === modal) closeModal();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !modal.hidden) closeModal();
    if (event.key === 'Enter' && !modal.hidden && document.activeElement === phraseInput) {
      event.preventDefault();
      confirmButton.click();
    }
  });
})();

/* Escáner compartido de códigos de barras y QR. */
document.addEventListener('DOMContentLoaded', () => {
  'use strict';
  const dialog = document.getElementById('ssModalCamara');
  if (!dialog) return;
  const estado = document.getElementById('ssCamaraEstado');
  let lector = null;
  let apertura = null;
  let cierre = null;
  let destino = null;
  let modalOrigen = null;
  let codigoAnterior = '';
  let consecutivos = 0;
  let finalizado = false;
  let movimientoPendiente = null;
  const longitudesGS1 = new Map([['EAN_13', 13], ['EAN_8', 8], ['UPC_A', 12]]);
  const guia = 'Centra el código completo, incluidos sus bordes claros. Si se ve borroso, aléjalo un poco. Si hay brillo, inclina el envase.';

  function esCodigoGS1Valido(codigo, longitud) {
    if (codigo.length !== longitud || !/^[0-9]+$/.test(codigo)) return false;
    let suma = 0;
    for (let i = codigo.length - 1; i >= 0; i--) {
      const desdeElFinal = codigo.length - 1 - i;
      suma += Number(codigo[i]) * (desdeElFinal % 2 ? 3 : 1);
    }
    return suma % 10 === 0;
  }

  function detener() {
    if (cierre || !lector) return cierre;
    const actual = lector;
    const iniciando = apertura;
    lector = null;
    apertura = null;
    cierre = (async () => {
      // Si el diálogo se cerró mientras se pedía permiso, la cámara puede
      // terminar de abrirse después del cierre. Libérala en ambos casos.
      try { await iniciando; } catch (_) { /* La apertura ya falló. */ }
      try { await actual.stop(); } catch (_) { /* Sin cámara activa. */ }
      try { actual.clear(); } catch (_) { /* El lector ya se liberó. */ }
    })().finally(() => { cierre = null; });
    return cierre;
  }

  async function iniciar(actual, opciones, onScan) {
    const camara = {facingMode: 'environment'};
    const sinCodigo = () => {};
    const permisoRechazado = error => /NotAllowedError|PermissionDenied|permission denied|SecurityError/i.test(String(error));
    try {
      await actual.start(camara, {
        ...opciones,
        videoConstraints: {
          facingMode: {ideal: 'environment'},
          width: {ideal: 1280},
          height: {ideal: 720},
        },
      }, onScan, sinCodigo);
    } catch (error) {
      if (lector !== actual || permisoRechazado(error)) throw error;
      try {
        await actual.start(camara, opciones, onScan, sinCodigo);
      } catch (fallo) {
        if (lector !== actual || permisoRechazado(fallo)) throw fallo;
        const camaras = await Html5Qrcode.getCameras();
        if (lector !== actual || !camaras.length) throw fallo;
        await actual.start(camaras[0].id, opciones, onScan, sinCodigo);
      }
    }
  }

  const modalCamara = bootstrap.Modal.getOrCreateInstance(dialog);
  document.querySelectorAll('.ss-scan-code').forEach(btn => {
    btn.addEventListener('click', () => {
      if (lector || cierre) return;
      destino = document.getElementById(btn.dataset.target);
      if (!destino || destino.disabled) return;
      modalOrigen = btn.closest('.modal');
      codigoAnterior = '';
      consecutivos = 0;
      finalizado = false;
      movimientoPendiente = null;
      estado.textContent = 'Abriendo la cámara…';
      if (modalOrigen) {
        const original = modalOrigen;
        original.addEventListener('hidden.bs.modal', () => modalCamara.show(), {once: true});
        bootstrap.Modal.getOrCreateInstance(original).hide();
      } else {
        modalCamara.show();
      }
    });
  });

  dialog.addEventListener('shown.bs.modal', async () => {
    if (!window.Html5Qrcode) {
      estado.textContent = 'No se pudo cargar el lector. Escribe el código manualmente.';
      return;
    }
    try {
      const actual = new Html5Qrcode('ssLectorCamara', {
        formatsToSupport: [
          Html5QrcodeSupportedFormats.EAN_13,
          Html5QrcodeSupportedFormats.EAN_8,
          Html5QrcodeSupportedFormats.UPC_A,
          Html5QrcodeSupportedFormats.UPC_E,
          Html5QrcodeSupportedFormats.CODE_128,
          Html5QrcodeSupportedFormats.CODE_39,
          Html5QrcodeSupportedFormats.QR_CODE,
        ],
        verbose: false,
      });
      lector = actual;
      const opciones = {
        fps: 10,
        qrbox: (ancho, alto) => {
          const anchoMarco = Math.floor(ancho * 0.78);
          return {
            width: anchoMarco,
            height: Math.min(Math.floor(anchoMarco * 0.55), Math.floor(alto * 0.78), 145),
          };
        },
      };
      const onScan = (codigo, lectura) => {
        if (lector !== actual || finalizado || !destino) return;
        codigo = String(codigo || '').trim();
        if (!codigo || codigo.length > 100) return;
        const formato = lectura?.result?.format?.formatName;
        const longitud = longitudesGS1.get(formato);
        if (longitud) {
          if (!esCodigoGS1Valido(codigo, longitud)) return;
        } else {
          consecutivos = codigo === codigoAnterior ? consecutivos + 1 : 1;
          codigoAnterior = codigo;
          if (consecutivos < 2) {
            estado.textContent = 'Mantén el código quieto un momento para confirmarlo.';
            return;
          }
        }
        finalizado = true;
        const editorIndividual = destino.dataset.codigosEditor === 'true';
        if (destino.id === 'editCodigosBarra' && !editorIndividual) {
          const actual = destino.value.split(',').map(s => s.trim()).filter(Boolean);
          if (!actual.includes(codigo)) actual.push(codigo);
          destino.value = actual.join(', ');
        } else {
          destino.value = codigo;
        }
        destino.dispatchEvent(new Event('input', {bubbles: true}));
        if (editorIndividual) {
          destino.dispatchEvent(new CustomEvent('smartstock:product-barcode-scanned', {
            detail: {codigo, tipo: formato === 'QR_CODE' ? 'QR' : formato ? 'BARRA' : null},
          }));
        }
        if (destino.id === 'inputEscaner') movimientoPendiente = codigo;
        modalCamara.hide();
      };
      apertura = iniciar(actual, opciones, onScan);
      try {
        await apertura;
      } catch (error) {
        if (lector !== actual) return;
        throw error;
      }
      if (lector !== actual) return;
      if (!consecutivos) estado.textContent = guia;
      try {
        const capacidades = actual.getRunningTrackCapabilities();
        if (capacidades.focusMode?.includes('continuous')) {
          await actual.applyVideoConstraints({advanced: [{focusMode: 'continuous'}]});
        }
      } catch (_) { /* La cámara conserva su enfoque predeterminado. */ }
    } catch (_) {
      estado.textContent = 'No se pudo abrir la cámara. Revisa el permiso o escribe el código manualmente.';
      detener();
    }
  });

  dialog.addEventListener('hide.bs.modal', detener);
  dialog.addEventListener('hidden.bs.modal', () => {
    detener();
    if (movimientoPendiente) {
      const codigo = movimientoPendiente;
      movimientoPendiente = null;
      window.dispatchEvent(new CustomEvent('smartstock:barcode-scanned', {detail: {codigo}}));
    }
    if (modalOrigen) {
      bootstrap.Modal.getOrCreateInstance(modalOrigen).show();
      modalOrigen = null;
    }
  });
});

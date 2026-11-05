/* Consulta operativa de stock por bodega. */
document.addEventListener('DOMContentLoaded', async () => {
    'use strict';
    const sesion = await window.SmartStockNavegacion.lista;
    if (!sesion) return;

    const el = id => document.getElementById(id);
    const selector = el('inicioBodegaSelector');
    const estado = el('inicioBodegaEstado');
    const error = el('inicioBodegaError');
    const reintentar = el('inicioBodegaReintentar');
    const resumen = el('inicioBodegaResumen');
    const accesos = [...document.querySelectorAll('[data-operacion]')]
        .map(enlace => ({enlace, ruta: enlace.getAttribute('href')}));
    const lista = el('inicioBodegaAlertas');
    const formato = new Intl.NumberFormat('es-CL');
    const nombre = sesion.usuario.nombre_completo || 'Usuario';
    el('user-name-sidebar').textContent = nombre;
    el('user-role-sidebar').textContent = sesion.usuario.rol_nombre || 'Administrador';
    el('user-avatar').src = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(nombre) + '&background=0f766e&color=fff';

    function actualizarAccesos(bodega) {
        for (const {enlace, ruta} of accesos) {
            enlace.hidden = !bodega || !sesion.modulos.includes(ruta);
            if (bodega) enlace.href = ruta + '?' + new URLSearchParams({bodega: bodega.id});
        }
    }

    function itemAlerta(alerta, bodega) {
        const item = document.createElement('li');
        item.className = 'list-group-item px-0 d-flex flex-wrap justify-content-between align-items-start gap-2';
        const producto = document.createElement('div');
        const titulo = document.createElement('strong');
        const stock = document.createElement('div');
        titulo.textContent = alerta.producto;
        stock.className = 'small text-muted';
        stock.textContent = alerta.sku + ' · Stock ' + formato.format(alerta.stock) + ' · Mínimo ' + formato.format(alerta.minimo);
        producto.append(titulo, stock);
        const etiqueta = document.createElement('span');
        const agotado = alerta.estado === 'agotado';
        etiqueta.className = agotado ? 'badge badge-soft-danger' : 'badge badge-soft-warning';
        etiqueta.textContent = agotado ? 'Agotado' : 'Stock bajo';
        const acciones = document.createElement('div');
        acciones.className = 'd-flex align-items-center flex-wrap gap-2';
        acciones.append(etiqueta);
        if (sesion.modulos.includes('/productos/')) {
            const ver = document.createElement('a');
            const parametros = new URLSearchParams({bodega: bodega.id, producto: alerta.producto_id, q: alerta.sku});
            ver.href = '/productos/?' + parametros;
            ver.className = 'btn btn-sm btn-outline-secondary';
            ver.textContent = 'Ver producto';
            ver.setAttribute('aria-label', 'Ver producto ' + alerta.producto);
            acciones.append(ver);
        }
        item.append(producto, acciones);
        return item;
    }

    let version = 0;
    async function cargar() {
        const actual = ++version;
        const parametros = new URLSearchParams();
        if (selector.value && !selector.disabled) parametros.set('bodega', selector.value);
        estado.textContent = 'Cargando existencias…';
        error.hidden = true;
        reintentar.hidden = true;
        resumen.hidden = true;
        actualizarAccesos(null);
        try {
            const {data} = await window.SmartStockReportes.json('/api/v1/productos/inicio-bodega/?' + parametros);
            if (actual !== version) return;
            const {bodegas, bodega, conteos, alertas} = data;
            selector.replaceChildren(...bodegas.map(item => new Option(item.nombre, item.id)));
            selector.disabled = !bodega;
            if (!bodega) {
                selector.append(new Option('Sin bodegas activas', ''));
                estado.textContent = 'No hay bodegas activas para consultar.';
                return;
            }
            selector.value = String(bodega.id);
            estado.textContent = '';
            actualizarAccesos(bodega);
            el('inicioBodegaBajo').textContent = formato.format(conteos.bajo);
            el('inicioBodegaAgotado').textContent = formato.format(conteos.agotado);
            const total = conteos.bajo + conteos.agotado;
            el('inicioBodegaResumenAlertas').textContent = total
                ? 'Mostrando ' + alertas.length + ' de ' + total + ' productos en ' + bodega.nombre + '.'
                : 'No hay productos con stock bajo ni agotados en ' + bodega.nombre + '.';
            lista.replaceChildren(...alertas.map(alerta => itemAlerta(alerta, bodega)));
            resumen.hidden = false;
        } catch (fallo) {
            if (actual !== version) return;
            estado.textContent = '';
            error.textContent = fallo.message;
            error.hidden = false;
            reintentar.hidden = false;
        }
    }

    selector.addEventListener('change', cargar);
    reintentar.addEventListener('click', cargar);
    cargar();
});

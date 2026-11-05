/* Organización física de las bodegas. Las asignaciones son referencias. */
document.addEventListener('DOMContentLoaded', async () => {
    'use strict';
    if (window.SmartStockNavegacion && !await window.SmartStockNavegacion.lista) return;
    if (!localStorage.getItem('access_token')) { window.location.replace('/'); return; }
    const el = id => document.getElementById(id);
    const nodo = (tag, clase, texto) => { const n = document.createElement(tag); if (clase) n.className = clase; if (texto !== undefined) n.textContent = String(texto ?? ''); return n; };
    const aviso = (id, texto = '') => { el(id).textContent = texto; el(id).hidden = !texto; };
    const textoError = v => Array.isArray(v) ? v.map(textoError).join(' ') : v && typeof v === 'object' ? Object.values(v).map(textoError).join(' ') : String(v ?? '');
    const entero = v => Number.isSafeInteger(Number(v)) && Number(v) > 0;
    const inicio = new URLSearchParams(window.location.search);
    let usuario = {}; try { usuario = JSON.parse(localStorage.getItem('usuario') || '{}') || {}; } catch (_) {}
    el('user-name-sidebar').textContent = usuario.nombre_completo || 'Usuario'; el('user-role-sidebar').textContent = usuario.rol_nombre || 'Sin rol';
    el('user-avatar').src = 'https://ui-avatars.com/api/?name=' + encodeURIComponent(usuario.nombre_completo || 'Usuario') + '&background=0f766e&color=fff';
    let renovacion;
    async function api(url, opciones = {}) {
        let token = localStorage.getItem('access_token'), respuesta;
        const enviar = () => fetch(url, {...opciones, cache: 'no-store', headers: {Authorization: 'Bearer ' + token, ...(opciones.body ? {'Content-Type': 'application/json'} : {})}});
        try {
            respuesta = await enviar();
            if (respuesta.status === 401) {
                if (!renovacion) renovacion = (async () => {
                    const refresh = localStorage.getItem('refresh_token'); if (!refresh) return false;
                    const r = await fetch('/api/v1/auth/refresh/', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({refresh})});
                    if (r.status >= 500) throw new Error('No se pudo renovar la sesión. Vuelve a intentarlo.');
                    if (!r.ok) return false;
                    const j = await r.json(), d = j.data || j;
                    if (!d.access) return false;
                    localStorage.setItem('access_token', d.access); if (d.refresh) localStorage.setItem('refresh_token', d.refresh); return true;
                })().finally(() => { renovacion = null; });
                if (await renovacion || token !== localStorage.getItem('access_token')) { token = localStorage.getItem('access_token'); respuesta = await enviar(); }
                else { window.smartstockClearSession(); window.location.replace('/'); throw new Error('La sesión expiró. Vuelve a iniciar sesión.'); }
            }
        } catch (e) { throw new Error(opciones.method ? 'No pudimos confirmar el resultado. Revisa el listado antes de volver a registrar.' : e.message || 'No se pudo conectar con el servidor.'); }
        let datos; try { datos = await respuesta.json(); } catch (_) { throw new Error('No se pudo leer la respuesta. Revisa el listado antes de reintentar.'); }
        if (!respuesta.ok || datos.success === false) {
            const error = new Error(textoError(datos.errores || datos.mensaje || datos.detail || datos) || 'No se pudo completar la operación.');
            error.status = respuesta.status; throw error;
        }
        return datos;
    }
    const recursos = [
        {nombre:'pasillos', etiqueta:'pasillo', padre:'bodega'},
        {nombre:'estanterias', etiqueta:'estantería', padre:'pasillo'},
        {nombre:'niveles', etiqueta:'nivel', padre:'estanteria'},
        {nombre:'espacios', etiqueta:'ubicación', padre:'nivel'},
    ].map(r => ({...r, pagina:1, total:0, totalSinFiltro:null, version:0, filas:[], cargando:false, cargado:false, error:'', timer:null}));
    let opciones = null, generacion = 0, guardando = false, productoId = inicio.get('producto') || '', productoContexto = null;
    const lista = {pagina:1, total:0, version:0, filas:[], timer:null};
    const productos = {pagina:1, version:0, total:0, cargando:false, timer:null};
    let codigoContexto = null, asignarContexto = null, retirarContexto = null;
    const modalCodigo = new bootstrap.Modal(el('modalCodigoUbicacion'));
    const modalAsignar = new bootstrap.Modal(el('modalAsignarUbicacion'));
    const modalRetirar = new bootstrap.Modal(el('modalRetirarUbicacion'));
    const bodegaId = () => el('bodegaUbicaciones').value;
    const bodegaActual = () => opciones?.bodegas.find(b => String(b.id) === bodegaId());
    const seleccion = i => el('elegir-' + recursos[i].nombre).value;
    const superior = i => i ? seleccion(i - 1) : bodegaId();
    const rutaSeleccionada = () => [bodegaActual()?.nombre, ...recursos.map((r,i) => r.filas.find(f => String(f.id) === seleccion(i))?.codigo)].filter(Boolean).join(' / ');
    const url = (recurso, extra = {}, bodega = bodegaId()) => '/api/v1/ubicaciones/' + recurso + '/?' + new URLSearchParams({bodega, ...extra});
    const paginaValida = d => Array.isArray(d.results) && Number.isInteger(d.count) && d.count >= 0;
    const vistaMovil = window.matchMedia?.('(max-width: 575.98px)');
    let pasoAbierto = 0, interaccion = 0;
    function actualizarPasos() {
        recursos.forEach((r,i) => {
            const abierto = !vistaMovil?.matches || pasoAbierto === i;
            el('paso-' + r.nombre).open = abierto;
            el('resumen-' + r.nombre).setAttribute('aria-expanded', String(abierto));
            el('resumen-' + r.nombre).tabIndex = vistaMovil?.matches ? 0 : -1;
        });
    }
    function abrirPaso(indice) { pasoAbierto = indice; actualizarPasos(); }
    function primerPendiente() { const n = recursos.findIndex((r,i) => !seleccion(i)); return n < 0 ? 3 : n; }
    function cerrarAdministracion(excepto = null) { document.querySelectorAll('.ss-location-manage[open]').forEach(m => { if (m !== excepto) m.open = false; }); }
    const vacios = ['Esta bodega aún no tiene pasillos.', 'Este pasillo aún no tiene estanterías.', 'Esta estantería aún no tiene niveles.', 'Este nivel aún no tiene ubicaciones.'];
    const padres = ['una bodega', 'un pasillo', 'una estantería', 'un nivel'];
    vistaMovil?.addEventListener('change', actualizarPasos);
    function actualizarURL() {
        const p = new URLSearchParams(); if (bodegaId()) p.set('bodega', bodegaId()); if (productoId) p.set('producto', productoId);
        window.history.replaceState(null, '', '/ubicaciones/' + (p.size ? '?' + p : ''));
    }
    function actualizarEstado() {
        const gestionar = Boolean(opciones?.permisos.gestionar && bodegaActual()?.activa);
        el('bodegaUbicaciones').disabled = guardando || !opciones?.bodegas.length;
        recursos.forEach((r,i) => {
            const disponible = Boolean(superior(i));
            const elegido = r.filas.find(f => String(f.id) === seleccion(i));
            el('seleccion-' + r.nombre).textContent = elegido?.codigo || (r.cargando ? 'Cargando…' : r.error ? 'Carga pendiente' : r.cargado ? 'Sin selección' : 'Pendiente');
            el('buscador-' + r.nombre).hidden = !el('buscar-' + r.nombre).value && !(r.totalSinFiltro > 10);
            const estado = r.error || (r.cargando ? 'Cargando opciones…' : !disponible ? 'Selecciona ' + padres[i] + ' para continuar.' : r.cargado && !r.total ? (el('buscar-' + r.nombre).value ? 'No hay códigos que coincidan con la búsqueda.' : vacios[i]) : '');
            aviso('estado-' + r.nombre, estado);
            el('paginas-' + r.nombre).hidden = r.total <= 25 && r.pagina <= 1;
            el('numeracion-' + r.nombre).textContent = r.total ? 'Página ' + r.pagina + ' de ' + Math.ceil(r.total / 25) : '';
            el('buscar-' + r.nombre).disabled = guardando || !disponible;
            el('elegir-' + r.nombre).disabled = guardando || r.cargando || !r.filas.length;
            ['nuevo','editar','eliminar'].forEach(a => {
                const b = document.querySelector('[data-' + a + '="' + r.nombre + '"]'); b.hidden = !gestionar;
                b.disabled = guardando || r.cargando || !disponible || (a !== 'nuevo' && !seleccion(i));
            });
            el('anterior-' + r.nombre).disabled = guardando || r.cargando || r.pagina <= 1;
            el('siguiente-' + r.nombre).disabled = guardando || r.cargando || r.pagina * 25 >= r.total;
            const administrar = el('administrar-' + r.nombre);
            administrar.hidden = !gestionar || !elegido || r.cargando;
            if (administrar.hidden) administrar.open = false;
        });
        el('asignarProductoUbicacion').hidden = !gestionar;
        el('asignarProductoUbicacion').disabled = guardando || !seleccion(3) || productoContexto?.activo === false;
        el('soloUbicacion').disabled = guardando || !seleccion(3);
        el('rutaUbicaciones').textContent = seleccion(3) ? 'Ruta seleccionada: ' + rutaSeleccionada() : seleccion(2) && recursos[3].cargado && !recursos[3].total && !el('buscar-espacios').value ? 'Crea una ubicación dentro del nivel seleccionado para poder asignar productos.' : 'Selecciona o crea una ubicación para habilitar la asignación de productos.';
        el('guardarAsignacionUbicacion').disabled = guardando || productos.cargando || !asignarContexto || !el('productoAsignarUbicacion').value;
        el('buscarProductoUbicacion').disabled = guardando;
        el('codigoUbicacion').disabled = guardando;
        el('productoAsignarUbicacion').disabled = guardando || productos.cargando || ![...el('productoAsignarUbicacion').options].some(o => o.value && !o.disabled);
        el('anteriorProductoUbicacion').disabled = guardando || productos.cargando || productos.pagina <= 1;
        el('siguienteProductoUbicacion').disabled = guardando || productos.cargando || productos.pagina * 25 >= productos.total;
        el('anteriorProductoUbicacion').hidden = el('siguienteProductoUbicacion').hidden = productos.total <= 25 && productos.pagina <= 1;
        for (const id of ['modalCodigoUbicacion','modalAsignarUbicacion','modalRetirarUbicacion']) el(id).querySelectorAll('[data-bs-dismiss]').forEach(b => { b.disabled = guardando; });
        el('guardarCodigoUbicacion').disabled = guardando; el('confirmarRetirarUbicacion').disabled = guardando;
        actualizarPasos();
    }
    function resetDesde(indice) {
        for (let i=indice;i<recursos.length;i++) {
            const r=recursos[i]; ++r.version; clearTimeout(r.timer); r.filas=[]; r.pagina=1; r.total=0; r.totalSinFiltro=null; r.cargando=false; r.cargado=false; r.error='';
            el('buscar-' + r.nombre).value=''; el('elegir-' + r.nombre).replaceChildren(new Option(i ? 'Selecciona ' + recursos[i-1].etiqueta : 'Sin bodegas', ''));
            el('estado-' + r.nombre).textContent=''; el('reintentar-' + r.nombre).hidden=true;
        }
        actualizarEstado();
    }
    async function cargarPaso(indice, preferido = '', ultima = false) {
        if(el('soloUbicacion').checked){el('soloUbicacion').checked=false;lista.pagina=1;cargarAsignaciones();}
        const r=recursos[indice], padre=superior(indice); resetDesde(indice+1); if (!padre) return;
        const version=++r.version, epoca=generacion;
        r.cargando=true; r.cargado=false; r.error=''; r.filas=[]; el('elegir-' + r.nombre).replaceChildren(new Option('Cargando…','')); el('reintentar-' + r.nombre).hidden=true; actualizarEstado();
        try {
            const d=await api(url(r.nombre,{...(indice ? {[r.padre]:padre} : {}),page:ultima?'last':r.pagina,search:el('buscar-'+r.nombre).value.trim()}));
            if(version!==r.version||epoca!==generacion)return;
            if(!paginaValida(d)||d.results.some(f=>!entero(f.id)||typeof f.codigo!=='string'||String(f.padre_id)!==String(padre)))throw new Error('La estructura recibida no corresponde a la selección. Reintenta la carga.');
            r.filas=d.results;r.total=d.count;r.cargado=true;if(!el('buscar-'+r.nombre).value)r.totalSinFiltro=d.count;if(ultima)r.pagina=Math.max(1,Math.ceil(r.total/25));
            el('elegir-'+r.nombre).replaceChildren(new Option(d.results.length?'Selecciona '+r.etiqueta:'Sin opciones disponibles',''),...d.results.map(f=>new Option(f.codigo,String(f.id))));
            el('elegir-'+r.nombre).value=String(d.results.find(f=>String(f.id)===String(preferido))?.id||d.results[0]?.id||'');
        } catch(e) {
            if(version!==r.version||epoca!==generacion)return;
            if(e.status===404&&r.pagina>1&&!ultima)return cargarPaso(indice,preferido,true);
            r.total=0;r.error=e.message;el('elegir-'+r.nombre).replaceChildren(new Option('Carga pendiente',''));el('reintentar-'+r.nombre).hidden=false;
        } finally { if(version===r.version&&epoca===generacion){r.cargando=false;actualizarEstado();} }
        if(version===r.version&&epoca===generacion&&seleccion(indice)&&indice<3)await cargarPaso(indice+1);
    }
    function mensajeTabla(texto) { const tr=nodo('tr'),td=nodo('td','text-center text-muted p-4',texto);td.colSpan=4;tr.append(td);el('filasAsignaciones').replaceChildren(tr); }
    function filaAsignacion(a) {
        const tr=nodo('tr','ss-location-row');
        const producto=nodo('td');producto.dataset.label='Producto';producto.append(nodo('strong','ss-location-name',a.producto),nodo('span','ss-location-meta','SKU: '+a.sku));
        const ubicacion=nodo('td');ubicacion.dataset.label='Ubicación';ubicacion.append(nodo('span','',Object.values(a.ruta).join(' / ')));
        if(a.cantidad_heredada!==0)ubicacion.append(nodo('span','ss-location-meta','Cantidad heredada: '+a.cantidad_heredada+'. Requiere revisión antes de retirar la referencia.'));
        const estado=nodo('td');estado.dataset.label='Estado';estado.append(nodo('span','ss-bodegas-badge'+(a.activo?' activa':''),a.activo?'Activo':'Inactivo'));
        const acciones=nodo('td');
        if(opciones.permisos.gestionar&&bodegaActual()?.activa){const b=nodo('button','btn btn-sm btn-outline-danger','Retirar referencia');b.type='button';b.dataset.retirar=String(a.id);b.disabled=a.cantidad_heredada!==0||guardando;b.setAttribute('aria-label','Retirar ubicación de '+a.producto);acciones.append(b);}else acciones.append(nodo('span','small text-muted','Solo lectura'));
        tr.append(producto,ubicacion,estado,acciones);return tr;
    }
    function paginarLista() {
        const cont=el('paginasAsignaciones'),paginas=Math.ceil(lista.total/25);cont.replaceChildren();if(paginas<=1)return;
        const agregar=(texto,n,desactivado=false)=>{const b=nodo('button','btn btn-sm '+(n===lista.pagina?'btn-primary':'btn-outline-secondary'),texto);b.type='button';b.dataset.page=String(n);b.disabled=desactivado||n===lista.pagina;if(n===lista.pagina)b.setAttribute('aria-current','page');cont.append(b);};
        agregar('Anterior',lista.pagina-1,lista.pagina===1);const ns=new Set([1,paginas]);for(let n=Math.max(1,lista.pagina-1);n<=Math.min(paginas,lista.pagina+1);n++)ns.add(n);
        let previo=0;[...ns].sort((a,b)=>a-b).forEach(n=>{if(previo&&n>previo+1)cont.append(nodo('span','','…'));agregar(String(n),n);previo=n;});agregar('Siguiente',lista.pagina+1,lista.pagina===paginas);
    }
    async function cargarAsignaciones(ultima=false) {
        clearTimeout(lista.timer);if(!bodegaId())return;
        const version=++lista.version,epoca=generacion;lista.filas=[];mensajeTabla('Cargando…');el('resumenAsignaciones').textContent='Cargando referencias…';el('filasAsignaciones').setAttribute('aria-busy','true');el('paginasAsignaciones').replaceChildren();aviso('errorAsignaciones');el('reintentarAsignaciones').hidden=true;
        try {
            const d=await api(url('asignaciones',{page:ultima?'last':lista.pagina,search:el('buscarAsignaciones').value.trim(),...(productoId?{producto:productoId}:{}),...(el('soloUbicacion').checked&&seleccion(3)?{ubicacion:seleccion(3)}:{})}));
            if(version!==lista.version||epoca!==generacion)return;
            if(!paginaValida(d)||d.results.some(a=>!entero(a.id)||!entero(a.producto_id)||typeof a.producto!=='string'||typeof a.sku!=='string'||!a.ruta||['pasillo','estanteria','nivel','ubicacion'].some(k=>typeof a.ruta[k]!=='string')||!Number.isInteger(a.cantidad_heredada)))throw new Error('El listado de ubicaciones no se pudo leer.');
            lista.filas=d.results;lista.total=d.count;if(ultima)lista.pagina=Math.max(1,Math.ceil(lista.total/25));
            if(d.results.length)el('filasAsignaciones').replaceChildren(...d.results.map(filaAsignacion));else mensajeTabla('No hay productos asignados para estos filtros.');
            el('resumenAsignaciones').textContent=d.count?'Mostrando '+((lista.pagina-1)*25+1)+'–'+((lista.pagina-1)*25+d.results.length)+' de '+d.count+' referencias':'0 referencias';paginarLista();
        }catch(e){if(version!==lista.version||epoca!==generacion)return;if(e.status===404&&lista.pagina>1&&!ultima)return cargarAsignaciones(true);aviso('errorAsignaciones',e.message);mensajeTabla('No se pudo cargar el listado.');el('reintentarAsignaciones').hidden=false;}
        finally{if(version===lista.version&&epoca===generacion)el('filasAsignaciones').setAttribute('aria-busy','false');}
    }
    async function cambiarBodega() {
        const marca = ++interaccion; abrirPaso(0); cerrarAdministracion();
        ++generacion;++lista.version;lista.pagina=1;el('soloUbicacion').checked=false;resetDesde(0);actualizarURL();
        el('estadoBodegaUbicaciones').textContent=!bodegaId()?'Crea una bodega para organizar sus ubicaciones.':!bodegaActual().activa?'Bodega inactiva: consulta disponible, edición deshabilitada.':opciones.permisos.gestionar?'Puedes organizar la estructura y asignar productos.':'Consulta de ubicaciones. Solicita al encargado los cambios de estructura.';
        if(!bodegaId()){mensajeTabla('No hay bodegas disponibles.');return;}
        const epoca = generacion; cargarAsignaciones(); await cargarPaso(0);
        if (epoca === generacion && marca === interaccion) abrirPaso(primerPendiente());
    }
    async function iniciar() {
        aviso('errorUbicaciones');el('reintentarUbicaciones').hidden=true;
        try {
            const j=await api('/api/v1/ubicaciones/opciones/'),d=j.data;
            if(!d||typeof d.permisos?.ver!=='boolean'||typeof d.permisos.gestionar!=='boolean'||!Array.isArray(d.bodegas)||d.bodegas.some(b=>!entero(b.id)||typeof b.nombre!=='string'||typeof b.activa!=='boolean'))throw new Error('No se pudieron leer las opciones de ubicaciones.');
            opciones=d;
            if(!d.permisos.ver){aviso('errorUbicaciones','No tienes permiso para consultar ubicaciones. Solicita acceso a un administrador.');return;}
            [['menu-auditoria',d.menu?.auditoria],['menu-usuarios',d.menu?.usuarios],['menu-config',d.menu?.configuracion],['menu-sistema-title',d.menu?.usuarios||d.menu?.configuracion]].forEach(([id,visible])=>{el(id).hidden=!visible;});
            el('bodegaUbicaciones').replaceChildren(...d.bodegas.map(b=>new Option(b.nombre+(b.activa?'':' (inactiva)'),String(b.id))));
            const pedido=inicio.get('bodega');
            if(pedido&&!d.bodegas.some(b=>String(b.id)===pedido))throw new Error('La bodega solicitada no está disponible. Vuelve a Bodegas y selecciona una válida.');
            el('bodegaUbicaciones').value=pedido||String(d.bodegas.find(b=>b.activa&&b.nombre==='Bodega Central')?.id||d.bodegas.find(b=>b.activa)?.id||d.bodegas[0]?.id||'');
            el('panelUbicaciones').hidden=false;
            if(productoId){
                el('todosProductosUbicaciones').hidden=false;el('contextoProducto').hidden=false;
                const p=await api(url('productos',{producto:productoId}));
                if(!paginaValida(p)||p.results.length!==1||String(p.results[0].id)!==productoId)throw new Error('El producto solicitado no está disponible. Puedes quitar el filtro para consultar los demás.');
                productoContexto=p.results[0];el('contextoProducto').textContent=productoContexto.nombre+' · SKU '+productoContexto.sku+(productoContexto.activo?'':' · Inactivo: reactívalo antes de asignar.');
            }
            cambiarBodega();
        }catch(e){aviso('errorUbicaciones',e.message);el('reintentarUbicaciones').hidden=false;}
    }
    recursos.forEach((r,i)=>{
        el('resumen-'+r.nombre).addEventListener('click',e=>{e.preventDefault();if(vistaMovil?.matches&&!guardando){++interaccion;cerrarAdministracion();abrirPaso(i);}});
        el('elegir-'+r.nombre).addEventListener('change',()=>{++interaccion;cerrarAdministracion();abrirPaso(Math.min(i+1,3));resetDesde(i+1);if(i<3&&seleccion(i))cargarPaso(i+1);if(el('soloUbicacion').checked){el('soloUbicacion').checked=false;lista.pagina=1;cargarAsignaciones();}actualizarEstado();});
        el('buscar-'+r.nombre).addEventListener('input',()=>{++interaccion;abrirPaso(i);++r.version;resetDesde(i+1);r.filas=[];r.error='';el('elegir-'+r.nombre).replaceChildren(new Option('Buscando…',''));r.cargando=true;actualizarEstado();clearTimeout(r.timer);r.pagina=1;r.timer=setTimeout(()=>cargarPaso(i),300);if(el('soloUbicacion').checked){el('soloUbicacion').checked=false;cargarAsignaciones();}});
        el('anterior-'+r.nombre).addEventListener('click',()=>{++interaccion;r.pagina--;cargarPaso(i);});el('siguiente-'+r.nombre).addEventListener('click',()=>{++interaccion;r.pagina++;cargarPaso(i);});el('reintentar-'+r.nombre).addEventListener('click',()=>cargarPaso(i));
    });
    el('bodegaUbicaciones').addEventListener('change',cambiarBodega);el('reintentarUbicaciones').addEventListener('click',iniciar);
    el('reintentarAsignaciones').addEventListener('click',()=>cargarAsignaciones());
    el('buscarAsignaciones').addEventListener('input',()=>{++lista.version;lista.pagina=1;lista.filas=[];mensajeTabla('Buscando…');clearTimeout(lista.timer);lista.timer=setTimeout(()=>cargarAsignaciones(),300);});
    el('filtrosAsignaciones').addEventListener('submit',e=>{e.preventDefault();lista.pagina=1;cargarAsignaciones();});
    el('soloUbicacion').addEventListener('change',()=>{lista.pagina=1;cargarAsignaciones();});
    el('limpiarAsignaciones').addEventListener('click',()=>{el('filtrosAsignaciones').reset();lista.pagina=1;cargarAsignaciones();});
    el('todosProductosUbicaciones').addEventListener('click',()=>{productoId='';productoContexto=null;el('contextoProducto').hidden=true;el('todosProductosUbicaciones').hidden=true;aviso('errorUbicaciones');actualizarURL();cambiarBodega();});
    el('paginasAsignaciones').addEventListener('click',e=>{const b=e.target.closest('[data-page]');if(b&&!b.disabled){lista.pagina=Number(b.dataset.page);cargarAsignaciones();}});
    document.querySelector('.ss-location-grid').addEventListener('click',e=>{
        if(guardando)return;
        const b=e.target.closest('[data-nuevo],[data-editar],[data-eliminar]');if(!b||b.disabled)return;
        ++interaccion; cerrarAdministracion();
        const nombre=b.dataset.nuevo||b.dataset.editar||b.dataset.eliminar,i=recursos.findIndex(r=>r.nombre===nombre),r=recursos[i],id=seleccion(i),objeto=r.filas.find(f=>String(f.id)===id);
        if(b.dataset.eliminar){retirarContexto={recurso:nombre,id,indice:i,generacion,bodega:bodegaId()};el('tituloRetirarUbicacion').textContent='Eliminar '+r.etiqueta;el('descripcionRetirarUbicacion').textContent='¿Eliminar '+r.etiqueta+' '+objeto.codigo+' de '+bodegaActual().nombre+'? Solo se eliminará si no contiene estructura ni productos asignados.';aviso('errorRetirarUbicacion');modalRetirar.show();return;}
        codigoContexto={recurso:nombre,id:b.dataset.editar?id:'',indice:i,padre:superior(i),generacion,bodega:bodegaId()};
        el('tituloCodigoUbicacion').textContent=(codigoContexto.id?'Editar ':'Crear ')+r.etiqueta;el('padreCodigoUbicacion').textContent=[bodegaActual().nombre,...recursos.slice(0,i).map((v,k)=>v.filas.find(f=>String(f.id)===seleccion(k))?.codigo)].join(' / ');
        el('codigoUbicacion').value=codigoContexto.id?objeto.codigo:'';aviso('errorCodigoUbicacion');modalCodigo.show();
    });
    async function guardar(contexto, errorId, operacion, despues) {
        if(guardando||!contexto||contexto.generacion!==generacion)return;
        guardando=true;actualizarEstado();aviso(errorId);
        try{const r=await operacion();window.dispatchEvent(new Event('smartstock:notifications-changed'));guardando=false;actualizarEstado();if(contexto.generacion===generacion)despues(r);}
        catch(e){if(contexto.generacion===generacion)aviso(errorId,e.message);}
        finally{guardando=false;actualizarEstado();}
    }
    el('formCodigoUbicacion').addEventListener('submit',e=>{
        e.preventDefault();const c=codigoContexto;if(!c||!el('codigoUbicacion').value.trim())return;
        const r=recursos[c.indice],cuerpo={codigo:el('codigoUbicacion').value.trim(),...(!c.id&&c.indice?{[r.padre]:Number(c.padre)}:{})};
        guardar(c,'errorCodigoUbicacion',()=>api(url(c.recurso+(c.id?'/'+c.id:''),{},c.bodega),{method:c.id?'PATCH':'POST',body:JSON.stringify(cuerpo)}),j=>{
            modalCodigo.hide();r.pagina=1;abrirPaso(c.indice);el('buscar-'+r.nombre).value=r.totalSinFiltro!==null&&r.totalSinFiltro<25?'':j.data.codigo;
            const marca=interaccion;cargarPaso(c.indice,j.data.id).then(()=>{if(!c.id&&c.generacion===generacion&&marca===interaccion)abrirPaso(primerPendiente());});cargarAsignaciones();
        });
    });
    async function cargarProductos(ultima=false) {
        clearTimeout(productos.timer);const c=asignarContexto;if(!c)return;
        const version=++productos.version;productos.cargando=true;el('productoAsignarUbicacion').replaceChildren(new Option('Cargando…',''));el('productoAsignarUbicacion').disabled=true;el('reintentarProductoUbicacion').hidden=true;actualizarEstado();
        el('anteriorProductoUbicacion').disabled=true;el('siguienteProductoUbicacion').disabled=true;
        try {
            const d=await api(url('productos',{page:ultima?'last':productos.pagina,search:el('buscarProductoUbicacion').value.trim(),...(productoId?{producto:productoId}:{})},c.bodega));
            if(version!==productos.version||c!==asignarContexto||c.generacion!==generacion)return;
            if(!paginaValida(d)||d.results.some(p=>!entero(p.id)||typeof p.nombre!=='string'||typeof p.sku!=='string'||typeof p.activo!=='boolean'))throw new Error('No se pudieron leer los productos.');
            productos.total=d.count;if(ultima)productos.pagina=Math.max(1,Math.ceil(d.count/25));
            el('productoAsignarUbicacion').replaceChildren(new Option(d.results.length?'Selecciona un producto':'Sin productos para esta búsqueda',''),...d.results.map(p=>{const o=new Option(p.nombre+' · '+p.sku+(p.activo?'':' (inactivo)'),String(p.id));o.disabled=!p.activo;return o;}));
            if(productoId&&d.results[0]?.activo)el('productoAsignarUbicacion').value=productoId;
            el('productoAsignarUbicacion').disabled=!d.results.some(p=>p.activo);el('estadoProductoUbicacion').textContent=d.count>25?'Página '+productos.pagina+' de '+Math.ceil(d.count/25):d.count+' productos';
            el('anteriorProductoUbicacion').disabled=productos.pagina<=1;el('siguienteProductoUbicacion').disabled=productos.pagina*25>=d.count;
        }catch(e){if(version!==productos.version||c!==asignarContexto)return;if(e.status===404&&productos.pagina>1&&!ultima)return cargarProductos(true);productos.total=0;el('estadoProductoUbicacion').textContent=e.message;el('reintentarProductoUbicacion').hidden=false;}
        finally{if(version===productos.version&&c===asignarContexto){productos.cargando=false;actualizarEstado();}}
    }
    el('asignarProductoUbicacion').addEventListener('click',()=>{
        if(guardando||!seleccion(3))return;asignarContexto={bodega:bodegaId(),ubicacion:seleccion(3),generacion};productos.pagina=1;
        el('buscarProductoUbicacion').value='';el('busquedaAsignarUbicacion').hidden=Boolean(productoId);el('destinoAsignarUbicacion').textContent=rutaSeleccionada();aviso('errorAsignarUbicacion');modalAsignar.show();cargarProductos();
    });
    el('buscarProductoUbicacion').addEventListener('input',()=>{++productos.version;productos.cargando=true;el('productoAsignarUbicacion').replaceChildren(new Option('Buscando…',''));el('productoAsignarUbicacion').disabled=true;productos.pagina=1;clearTimeout(productos.timer);actualizarEstado();productos.timer=setTimeout(()=>cargarProductos(),300);});
    el('productoAsignarUbicacion').addEventListener('change',actualizarEstado);el('reintentarProductoUbicacion').addEventListener('click',()=>cargarProductos());
    el('anteriorProductoUbicacion').addEventListener('click',()=>{productos.pagina--;cargarProductos();});el('siguienteProductoUbicacion').addEventListener('click',()=>{productos.pagina++;cargarProductos();});
    el('formAsignarUbicacion').addEventListener('submit',e=>{
        e.preventDefault();const c=asignarContexto,p=el('productoAsignarUbicacion').value;if(!c||!entero(p)||productos.cargando)return;
        guardar(c,'errorAsignarUbicacion',()=>api(url('asignaciones',{},c.bodega),{method:'POST',body:JSON.stringify({producto_id:Number(p),ubicacion_id:Number(c.ubicacion)})}),()=>{modalAsignar.hide();lista.pagina=1;cargarAsignaciones();});
    });
    el('filasAsignaciones').addEventListener('click',e=>{
        const b=e.target.closest('[data-retirar]');if(!b||b.disabled||guardando)return;const a=lista.filas.find(f=>String(f.id)===b.dataset.retirar);if(!a)return;
        retirarContexto={recurso:'asignaciones',id:a.id,generacion,bodega:bodegaId()};el('tituloRetirarUbicacion').textContent='Retirar referencia';el('descripcionRetirarUbicacion').textContent='¿Retirar la ubicación '+Object.values(a.ruta).join(' / ')+' de '+a.producto+' en '+bodegaActual().nombre+'? El stock se conserva.';aviso('errorRetirarUbicacion');modalRetirar.show();
    });
    el('formRetirarUbicacion').addEventListener('submit',e=>{
        e.preventDefault();const c=retirarContexto;if(!c)return;
        guardar(c,'errorRetirarUbicacion',()=>api(url(c.recurso+'/'+c.id,{},c.bodega),{method:'DELETE'}),()=>{modalRetirar.hide();if(c.indice!==undefined)cargarPaso(c.indice);cargarAsignaciones();});
    });
    for(const id of ['modalCodigoUbicacion','modalAsignarUbicacion','modalRetirarUbicacion'])el(id).addEventListener('hide.bs.modal',e=>{if(guardando)e.preventDefault();});
    el('modalCodigoUbicacion').addEventListener('shown.bs.modal',()=>el('codigoUbicacion').focus());
    el('modalCodigoUbicacion').addEventListener('hidden.bs.modal',()=>{codigoContexto=null;});
    el('modalAsignarUbicacion').addEventListener('hidden.bs.modal',()=>{asignarContexto=null;++productos.version;clearTimeout(productos.timer);});
    el('modalRetirarUbicacion').addEventListener('hidden.bs.modal',()=>{retirarContexto=null;});
    document.addEventListener('click',e=>document.querySelectorAll('.ss-location-manage[open]').forEach(m=>{if(!m.contains(e.target))m.open=false;}));
    document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.ss-location-manage[open]').forEach(m=>{m.open=false;m.querySelector('summary').focus();});});
    iniciar();
});

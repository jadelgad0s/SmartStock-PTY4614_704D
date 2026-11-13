/* Gestión manual y confirmada de la cola SMS. Los GET nunca envían avisos. */
document.addEventListener('DOMContentLoaded',async ()=>{
    'use strict';
    if (window.SmartStockNavegacion && !await window.SmartStockNavegacion.lista) return;
    if(!localStorage.getItem('access_token')){window.location.replace('/');return;}
    const api=window.SmartStockSMS,el=id=>document.getElementById(id);
    const nodo=(tag,clase,texto)=>{const n=document.createElement(tag);if(clase)n.className=clase;if(texto!==undefined)n.textContent=String(texto??'');return n;};
    const aviso=(id,texto='')=>{el(id).textContent=texto;el(id).hidden=!texto;};
    const uuid=v=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
    const numero=v=>Number(v).toLocaleString('es-CL');
    let usuario={};try{usuario=JSON.parse(localStorage.getItem('usuario')||'{}')||{};}catch(_){}
    el('user-name-sidebar').textContent=usuario.nombre_completo||'Usuario';el('user-role-sidebar').textContent=usuario.rol_nombre||'Sin rol';
    el('user-avatar').src='https://ui-avatars.com/api/?name='+encodeURIComponent(usuario.nombre_completo||'Usuario')+'&background=0f766e&color=fff';
    const modal=new bootstrap.Modal(el('modalSMS'));
    let opciones=null,servicio=null,zona='America/Santiago',pagina=1,total=0,filas=[],revisables=0;
    let versionLista=0,versionServicio=0,versionModal=0,timer=null,listaCargando=false,servicioCargando=false,guardando=false,filtrosAplicados=null,contexto=null;
    const estados=new Set();
    function fecha(v){if(!v)return 'Sin registro';try{return new Intl.DateTimeFormat('es-CL',{dateStyle:'short',timeStyle:'short',timeZone:zona}).format(new Date(v));}catch(_){return 'Fecha no disponible';}}
    function parametros(){const p=new URLSearchParams();for(const [campo,id]of [['search','buscarSMS'],['estado','estadoSMS'],['bodega','bodegaSMS'],['desde','desdeSMS'],['hasta','hastaSMS']]){const v=el(id).value.trim();if(v)p.set(campo,v);}return p;}
    function filtrosValidos(){if(el('desdeSMS').value&&el('hastaSMS').value&&el('desdeSMS').value>el('hastaSMS').value){aviso('errorListaSMS','La fecha inicial no puede ser posterior a la final.');return false;}return true;}
    function puedePreparar(){return Boolean(opciones&&servicio?.activa&&servicio.configurada&&servicio.cuota_disponible>0&&filtrosAplicados&&revisables>0&&!listaCargando&&!servicioCargando&&!guardando);}
    function controles(){
        el('actualizarSMS').disabled=!opciones||guardando;el('prepararSMS').disabled=!puedePreparar();
        const estado=el('estadoSMS').value;
        el('ayudaProcesarSMS').textContent=estado&&estado!=='PENDIENTE'?'Selecciona Pendiente o Todos los estados para preparar una revisión.':servicio&&!servicio.activa?'Los envíos SMS están pausados en el servidor.':servicio&&!servicio.configurada?'Completa la configuración del servicio antes de procesar.':servicio&&servicio.cuota_disponible===0?'Se alcanzó el límite diario de intentos. Los avisos conservarán su estado pendiente.':'Revisa tandas de hasta 3 pendientes que coincidan con los filtros. Procesar puede consumir saldo de Twilio.';
        el('modalSMS').querySelectorAll('[data-bs-dismiss]').forEach(b=>{b.disabled=guardando;});
        el('confirmarModalSMS').disabled=guardando||!contexto||!['confirmar','cancelar'].includes(contexto.modo)||!contexto.envios.length;
        el('procesarAvisoSMS').disabled=guardando||!contexto?.envios[0]?.procesable;
        el('cancelarAvisoSMS').disabled=guardando||!contexto?.envios[0]?.cancelable;
        el('consultarResultadoSMS').disabled=guardando;
    }
    function envioValido(e){return e&&uuid(e.id)&&typeof e.producto==='string'&&typeof e.sku==='string'&&typeof e.bodega==='string'&&typeof e.destinatario==='string'&&estados.has(e.estado)&&typeof e.estado_etiqueta==='string'&&Number.isInteger(e.intentos)&&typeof e.procesable==='boolean'&&typeof e.cancelable==='boolean';}
    function badge(e){return nodo('span','ss-sms-status '+e.estado.toLowerCase(),e.estado_etiqueta);}
    function mensajeTabla(texto){const tr=nodo('tr'),td=nodo('td','text-center text-muted p-4',texto);td.colSpan=6;tr.append(td);el('filasSMS').replaceChildren(tr);}
    function fila(e){
        const tr=nodo('tr','ss-sms-row'),producto=nodo('td');producto.dataset.label='Producto y bodega';producto.append(nodo('strong','ss-sms-name',e.producto),nodo('span','ss-sms-meta','SKU: '+e.sku),nodo('span','ss-sms-meta',e.bodega));
        const destino=nodo('td','',e.destinatario);destino.dataset.label='Destinatario';
        const estado=nodo('td');estado.dataset.label='Estado';estado.append(badge(e));if(e.motivo)estado.append(nodo('span','ss-sms-meta',e.motivo));if(e.proximo_intento)estado.append(nodo('span','ss-sms-meta','Próxima revisión: '+fecha(e.proximo_intento)));
        const intentos=nodo('td','',e.intentos+' / 3');intentos.dataset.label='Intentos';const creada=nodo('td','',fecha(e.fecha));creada.dataset.label='Fecha';
        const acciones=nodo('td'),b=nodo('button','btn btn-sm btn-outline-secondary','Ver detalle');b.type='button';b.dataset.detalle=e.id;b.setAttribute('aria-label','Ver aviso SMS de '+e.producto);acciones.append(b);tr.append(producto,destino,estado,intentos,creada,acciones);return tr;
    }
    function paginar(){
        const cont=el('paginasSMS'),paginas=Math.ceil(total/25);cont.replaceChildren();if(paginas<=1)return;
        const agregar=(texto,n,disabled=false)=>{const b=nodo('button','btn btn-sm '+(n===pagina?'btn-primary':'btn-outline-secondary'),texto);b.type='button';b.dataset.page=String(n);b.disabled=disabled||n===pagina;if(n===pagina)b.setAttribute('aria-current','page');cont.append(b);};
        agregar('Anterior',pagina-1,pagina===1);const ns=new Set([1,paginas]);for(let n=Math.max(1,pagina-1);n<=Math.min(paginas,pagina+1);n++)ns.add(n);let previo=0;[...ns].sort((a,b)=>a-b).forEach(n=>{if(previo&&n>previo+1)cont.append(nodo('span','','…'));agregar(String(n),n);previo=n;});agregar('Siguiente',pagina+1,pagina===paginas);
    }
    function resumenFiltros(){el('resumenFiltrosSMS').textContent=[el('estadoSMS').selectedOptions[0]?.textContent,el('bodegaSMS').selectedOptions[0]?.textContent,el('buscarSMS').value? 'Búsqueda activa':''].filter(Boolean).join(' · ');}
    async function cargarServicio(){
        const version=++versionServicio;servicioCargando=true;controles();
        try{
            const j=await api.json('/api/v1/alertas-sms/estado/'),d=j.data;if(version!==versionServicio)return;
            if(!d||typeof d.activa!=='boolean'||typeof d.configurada!=='boolean'||!Array.isArray(d.destinatarios)||!Array.isArray(d.errores_configuracion)||['pendientes','revisables','por_confirmar','cuota_disponible','intentos_hoy','limite_diario'].some(k=>!Number.isInteger(d[k])||d[k]<0))throw new Error('El estado del servicio SMS no se pudo leer.');
            servicio=d;zona=d.zona_horaria||zona;el('servicioSMS').textContent=d.activa?(d.configurada?'SMS activos · Configuración lista':'SMS activos · Revisa la configuración'):'SMS pausados';
            el('presupuestoSMS').textContent='Hoy: '+numero(d.intentos_hoy)+' de '+numero(d.limite_diario)+' intentos';el('destinatariosSMS').textContent=d.destinatarios.length?'Destinatarios autorizados: '+d.destinatarios.join(', '):'Sin destinatarios configurados';
            el('configuracionSMS').replaceChildren(...d.errores_configuracion.map(t=>nodo('li','',t)));el('configuracionSMS').hidden=!d.errores_configuracion.length;
            [['totalPendientesSMS',d.pendientes],['totalRevisablesSMS',d.revisables],['totalInciertosSMS',d.por_confirmar],['totalDisponiblesSMS',d.cuota_disponible]].forEach(([id,n])=>{el(id).textContent=numero(n);});el('zonaSMS').textContent='Zona horaria: '+zona;aviso('errorSMS');
        }catch(e){if(version===versionServicio){servicio=null;aviso('errorSMS',e.message);el('reintentarSMS').hidden=false;}}
        finally{if(version===versionServicio){servicioCargando=false;controles();}}
    }
    async function cargarLista(ultima=false){
        clearTimeout(timer);if(!opciones)return;const version=++versionLista;listaCargando=true;filtrosAplicados=null;filas=[];mensajeTabla('Cargando historial…');el('paginasSMS').replaceChildren();el('filasSMS').setAttribute('aria-busy','true');aviso('errorListaSMS');el('reintentarListaSMS').hidden=true;resumenFiltros();controles();
        if(!filtrosValidos()){listaCargando=false;el('filasSMS').setAttribute('aria-busy','false');mensajeTabla('Revisa las fechas del filtro.');controles();return;}
        const p=parametros(),consulta=new URLSearchParams(p);consulta.set('page',ultima?'last':String(pagina));
        try{
            const d=await api.json('/api/v1/alertas-sms/historial/?'+consulta);if(version!==versionLista)return;
            if(!Number.isInteger(d.count)||d.count<0||!Number.isInteger(d.revisables)||d.revisables<0||!Array.isArray(d.results)||d.results.some(e=>!envioValido(e)))throw new Error('El historial SMS tiene un formato inválido.');
            total=d.count;filas=d.results;revisables=d.revisables;zona=d.zona_horaria||zona;if(ultima)pagina=Math.max(1,Math.ceil(total/25));filtrosAplicados=p;
            if(filas.length)el('filasSMS').replaceChildren(...filas.map(fila));else mensajeTabla('No hay avisos SMS que coincidan con los filtros.');
            el('conteoSMS').textContent=total?'Mostrando '+((pagina-1)*25+1)+'–'+((pagina-1)*25+filas.length)+' de '+total+' avisos':'0 avisos';paginar();
        }catch(e){if(version!==versionLista)return;if(e.status===404&&pagina>1&&!ultima)return cargarLista(true);aviso('errorListaSMS',e.message);mensajeTabla('No se pudo cargar el historial.');el('reintentarListaSMS').hidden=false;}
        finally{if(version===versionLista){listaCargando=false;el('filasSMS').setAttribute('aria-busy','false');controles();}}
    }
    async function actualizar(){el('reintentarSMS').hidden=true;await Promise.allSettled([cargarServicio(),cargarLista()]);}
    async function iniciar(){
        aviso('errorSMS');el('reintentarSMS').hidden=true;
        try{
            const p=await api.acceso();if(!p.ver){aviso('errorSMS','Solo los administradores pueden consultar y gestionar los SMS.');return;}
            const j=await api.json('/api/v1/alertas-sms/opciones/'),d=j.data;
            if(!d||!Array.isArray(d.bodegas)||!Array.isArray(d.estados)||d.estados.some(e=>typeof e.valor!=='string'||typeof e.etiqueta!=='string'))throw new Error('No se pudieron leer las opciones del historial SMS.');
            opciones=d;d.estados.forEach(e=>estados.add(e.valor));el('estadoSMS').replaceChildren(new Option('Todos los estados',''),...d.estados.map(e=>new Option(e.etiqueta,e.valor)));el('estadoSMS').value='PENDIENTE';
            el('bodegaSMS').replaceChildren(new Option('Todas las bodegas',''),...d.bodegas.map(b=>new Option(b.nombre+(b.activa?'':' (inactiva)'),String(b.id))));
            [['menu-auditoria',d.menu?.auditoria],['menu-usuarios',d.menu?.usuarios],['menu-config',d.menu?.configuracion],['menu-sistema-title',true]].forEach(([id,mostrar])=>{el(id).hidden=!mostrar;});
            el('detalleFiltrosSMS').open=!window.matchMedia?.('(max-width: 575.98px)').matches;el('panelSMS').hidden=false;await actualizar();
        }catch(e){aviso('errorSMS',e.message);el('reintentarSMS').hidden=false;}
    }
    function invalidar(){++versionLista;filtrosAplicados=null;filas=[];pagina=1;mensajeTabla('Actualizando filtros…');el('paginasSMS').replaceChildren();resumenFiltros();controles();}
    el('buscarSMS').addEventListener('input',()=>{invalidar();clearTimeout(timer);timer=setTimeout(()=>cargarLista(),300);});
    for(const id of ['estadoSMS','bodegaSMS','desdeSMS','hastaSMS'])el(id).addEventListener('change',()=>{invalidar();cargarLista();});
    el('filtrosSMS').addEventListener('submit',e=>{e.preventDefault();invalidar();cargarLista();});
    el('limpiarSMS').addEventListener('click',()=>{el('filtrosSMS').reset();el('estadoSMS').value='PENDIENTE';invalidar();cargarLista();});
    el('actualizarSMS').addEventListener('click',actualizar);el('reintentarSMS').addEventListener('click',()=>opciones?actualizar():iniciar());el('reintentarListaSMS').addEventListener('click',()=>cargarLista());
    el('paginasSMS').addEventListener('click',e=>{const b=e.target.closest('[data-page]');if(b&&!b.disabled){pagina=Number(b.dataset.page);cargarLista();}});
    function tarjeta(e){
        const div=nodo('article','ss-sms-record');div.append(nodo('strong','ss-sms-name',e.producto),nodo('span','ss-sms-meta','SKU: '+e.sku+' · '+e.bodega),badge(e));
        const dl=nodo('dl');for(const [titulo,valor]of [['Destinatario',e.destinatario],['Intentos',e.intentos+' / 3'],['Fecha',fecha(e.fecha)],['Último intento',fecha(e.ultimo_intento)],['Próxima revisión',fecha(e.proximo_intento)],['Stock / mínimo',e.stock+' / '+e.minimo]]){const campo=nodo('div');campo.append(nodo('dt','',titulo),nodo('dd','',valor));dl.append(campo);}div.append(dl);
        if(e.motivo)div.append(nodo('p','small mb-2',e.motivo));if(e.codigo_error)div.append(nodo('p','small mb-2','Código de error: '+e.codigo_error));if(e.detalle)div.append(nodo('p','small mb-2',e.detalle));if(e.twilio_sid)div.append(nodo('p','small ss-sms-meta','Identificador Twilio: '+e.twilio_sid));if(typeof e.mensaje==='string')div.append(nodo('pre','ss-sms-message',e.mensaje));return div;
    }
    function pintarModal(c){
        if(c!==contexto)return;
        el('contenidoModalSMS').replaceChildren(...c.envios.map(tarjeta));
        el('procesarAvisoSMS').hidden=c.modo!=='detalle'||c.envios[0]?.estado!=='PENDIENTE';el('cancelarAvisoSMS').hidden=c.modo!=='detalle'||!c.envios[0]?.cancelable;
        el('confirmarModalSMS').hidden=!['confirmar','cancelar'].includes(c.modo);el('consultarResultadoSMS').hidden=!['errorLectura','resultado','incierto','rechazado'].includes(c.modo);
        el('consultarResultadoSMS').textContent=c.modo==='errorLectura'?'Reintentar consulta':'Actualizar historial';
        el('confirmarModalSMS').textContent=c.modo==='cancelar'?'Confirmar cancelación':'Confirmar procesamiento';el('confirmarModalSMS').className='btn '+(c.modo==='cancelar'?'btn-warning':'btn-primary');
        el('tituloModalSMS').textContent=c.modo==='confirmar'?'Confirmar revisión de '+c.envios.length+' SMS':c.modo==='cancelar'?'Cancelar aviso pendiente':c.modo==='resultado'?'Resultado de la revisión':'Detalle del aviso SMS';
        el('ayudaModalSMS').textContent=c.modo==='confirmar'?'Se revisarán únicamente estos avisos. Se volverán a comprobar el stock, su estado y la cuota diaria. Procesar puede consumir saldo de Twilio.':c.modo==='cancelar'?'Se cancelará solo este aviso pendiente. Su historial y el stock se conservan.':c.modo==='incierto'?'Los avisos mostrados corresponden al estado previo a la solicitud. Actualiza el historial para comprobar el resultado; no vuelvas a enviar sin revisarlo.':'';
        controles();
    }
    function abrirContexto(tipo,id){
        const c={tipo,id,modo:'cargando',envios:[],abierto:true,version:++versionModal,filtros:new URLSearchParams(filtrosAplicados||parametros())};contexto=c;
        aviso('errorModalSMS');el('estadoModalSMS').textContent='Consultando avisos…';pintarModal(c);modal.show();return c;
    }
    async function consultarModal(c,confirmar=false){
        const version=++versionModal;c.version=version;c.modo='cargando';aviso('errorModalSMS');el('estadoModalSMS').textContent='Consultando avisos…';pintarModal(c);
        try{
            const j=await api.json(c.tipo==='lote'?'/api/v1/alertas-sms/preparar/?'+c.filtros:'/api/v1/alertas-sms/historial/'+encodeURIComponent(c.id)+'/');
            if(c!==contexto||!c.abierto||version!==c.version)return;
            const registros=c.tipo==='lote'?j.data?.envios:[j.data];
            if(!Array.isArray(registros)||registros.length>3||registros.some(e=>!envioValido(e)||typeof e.mensaje!=='string'))throw new Error('No se pudo preparar una selección válida de avisos.');
            if(c.tipo==='lote'&&c.filtros.toString()!==parametros().toString())throw new Error('Los filtros cambiaron. Cierra la ventana y prepara nuevamente la revisión.');
            c.envios=registros;c.modo=(c.tipo==='lote'||confirmar)&&registros.length&&registros.every(e=>e.procesable)?'confirmar':'detalle';
            el('estadoModalSMS').textContent=registros.length?'':'No hay avisos disponibles para procesar con estos filtros, la espera actual y la cuota diaria.';
            pintarModal(c);
        }catch(e){if(c===contexto&&version===c.version){c.modo='errorLectura';aviso('errorModalSMS',e.message);el('estadoModalSMS').textContent='';pintarModal(c);}}
    }
    el('filasSMS').addEventListener('click',e=>{const b=e.target.closest('[data-detalle]');if(b&&!guardando&&uuid(b.dataset.detalle))consultarModal(abrirContexto('detalle',b.dataset.detalle));});
    el('prepararSMS').addEventListener('click',()=>{if(puedePreparar())consultarModal(abrirContexto('lote'));});
    el('procesarAvisoSMS').addEventListener('click',()=>{if(contexto?.envios[0]?.procesable&&!guardando)consultarModal(contexto,true);});
    el('cancelarAvisoSMS').addEventListener('click',()=>{if(contexto?.envios[0]?.cancelable&&!guardando){contexto.modo='cancelar';el('estadoModalSMS').textContent='';pintarModal(contexto);}});
    el('consultarResultadoSMS').addEventListener('click',()=>{if(guardando||!contexto)return;if(contexto.modo==='errorLectura')consultarModal(contexto);else{modal.hide();actualizar();}});
    el('confirmarModalSMS').addEventListener('click',async()=>{
        const c=contexto;if(!c||guardando||!['confirmar','cancelar'].includes(c.modo)||!c.envios.length)return;
        if(c.tipo==='lote'&&c.filtros.toString()!==parametros().toString()){c.modo='rechazado';aviso('errorModalSMS','Los filtros cambiaron. Prepara nuevamente los avisos que quieres revisar.');pintarModal(c);return;}
        const cancelando=c.modo==='cancelar',ids=c.envios.map(e=>e.id);guardando=true;aviso('errorModalSMS');el('estadoModalSMS').textContent=cancelando?'Cancelando aviso…':'Revisando los avisos seleccionados. Puede tardar unos segundos…';controles();
        try{
            const j=await api.json(cancelando?'/api/v1/alertas-sms/historial/'+encodeURIComponent(ids[0])+'/cancelar/':'/api/v1/alertas-sms/procesar-pendientes/',{method:'POST',body:cancelando?{}:{ids}});
            if(c!==contexto)return;
            if(!cancelando&&(!Number.isInteger(j.data?.revisados)||!Array.isArray(j.data.resultados)||j.data.resultados.some(e=>!envioValido(e)))){const e=new Error('El resultado no se pudo confirmar. Actualiza el historial.');e.incierto=true;throw e;}
            c.modo='resultado';if(cancelando)c.envios=c.envios.map(e=>({...e,estado:'CANCELADO',estado_etiqueta:'Cancelado',procesable:false,cancelable:false,motivo:'',detalle:'Cancelado por un administrador desde Alertas SMS.'}));else c.envios=j.data.resultados;
            el('estadoModalSMS').textContent=j.mensaje||'Revisión completada.';window.dispatchEvent(new Event('smartstock:notifications-changed'));pintarModal(c);
            await actualizar();
        }catch(e){if(c===contexto){c.modo=e.incierto?'incierto':'rechazado';aviso('errorModalSMS',e.message);el('estadoModalSMS').textContent=e.incierto?'Resultado pendiente de comprobar.':'';pintarModal(c);}}
        finally{guardando=false;if(c===contexto)pintarModal(c);controles();}
    });
    el('modalSMS').addEventListener('hide.bs.modal',e=>{if(guardando)e.preventDefault();else if(contexto){contexto.abierto=false;++contexto.version;}});
    el('modalSMS').addEventListener('hidden.bs.modal',()=>{contexto=null;});
    iniciar();
});

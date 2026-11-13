const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../..');
let html=readFileSync(path.join(root,'templates/bodegas.html'),'utf8');
const nueva=readFileSync(path.join(root,'templates/alertas_sms.html'),'utf8');
for(const bloque of ['bodega_contenido','bodega_modales']){
 const patron=new RegExp('{% block '+bloque+' %}([\\s\\S]*?){% endblock %}');
 html=html.replace(patron,nueva.match(patron)[1]);
}
html=html.replace(/{% block enlace_sms %}[\s\S]*?{% endblock %}/,readFileSync(path.join(root,'templates/componentes/enlace_sms.html'),'utf8')).replace(/{%[\s\S]*?%}/g,'');
const base=readFileSync(path.join(root,'static/js/sms_base.js'),'utf8');
const fuente=readFileSync(path.join(root,'static/js/alertas_sms.js'),'utf8');
const tick=()=>new Promise(r=>setImmediate(r));
const id=n=>'10000000-0000-4000-8000-'+String(n).padStart(12,'0');
const etiquetas={PENDIENTE:'Pendiente',ENVIANDO:'Envío en curso',ACEPTADO:'Aceptado por Twilio',ENVIADO:'Enviado a la red',ENTREGADO:'Entregado',NO_ENTREGADO:'No entregado',RECHAZADO:'Rechazado',INCIERTO:'Resultado por confirmar',CANCELADO:'Cancelado'};
const aviso=(n=1,extra={})=>({id:id(n),producto:'Martillo '+n,sku:'P-'+n,bodega:'Bodega Central',bodega_id:1,destinatario:'+569*****661',estado:'PENDIENTE',estado_etiqueta:'Pendiente',intentos:0,stock:5,minimo:5,fecha:'2026-11-02T12:00:00Z',ultimo_intento:null,proximo_intento:null,twilio_sid:'',motivo:'Disponible para revisar.',codigo_error:'',detalle:'',procesable:true,cancelable:true,mensaje:'SmartStock - Stock bajo\nMartillo '+n+'\nQuedan 5 unidades.',...extra});
const servicio=extra=>({data:{activa:true,configurada:true,destinatarios:['+569*****661'],errores_configuracion:[],pendientes:4,revisables:3,por_confirmar:1,cuota_disponible:8,intentos_hoy:2,limite_diario:10,zona_horaria:'America/Santiago',...extra}});
const opciones=()=>({data:{bodegas:[{id:1,nombre:'Bodega Central',activa:true},{id:2,nombre:'Bodega Norte',activa:true}],estados:Object.entries(etiquetas).map(([valor,etiqueta])=>({valor,etiqueta})),menu:{auditoria:true,usuarios:true,configuracion:true}}});
const pagina=(results=[aviso()],count=results.length,revisables=results.filter(e=>e.procesable).length)=>({count,results,revisables,zona_horaria:'America/Santiago'});
async function pantalla(t,{mobile=false,soloMenu=false}={}){
 const dom=new JSDOM(soloMenu?'<li id="menu-sms" hidden></li>':html,{url:'http://localhost/'+(soloMenu?'productos/':'alertas-sms/'),runScripts:'outside-only',pretendToBeVisual:true});t.after(()=>dom.window.close());
 const w=dom.window,requests=[],timers=new Map();let numero=0;
 w.localStorage.setItem('access_token','inicial');w.localStorage.setItem('refresh_token','renovar');w.localStorage.setItem('smartstock-theme','dark');w.localStorage.setItem('usuario',JSON.stringify({nombre_completo:'Administrador Demo',rol_nombre:'Administrador'}));
 w.matchMedia=()=>({matches:mobile});w.smartstockClearSession=()=>{};
 w.setTimeout=(fn,delay)=>{timers.set(++numero,{fn,delay});return numero;};w.clearTimeout=i=>timers.delete(i);
 w.bootstrap={Modal:class{constructor(n){this.n=n;}show(){this.n.classList.add('show');}hide(){const e=new w.Event('hide.bs.modal',{cancelable:true});this.n.dispatchEvent(e);if(!e.defaultPrevented){this.n.classList.remove('show');this.n.dispatchEvent(new w.Event('hidden.bs.modal'));}}}};
 w.fetch=(url,options={})=>new Promise((resolve,reject)=>requests.push({url:new URL(url,w.location.href),options,resolve,reject,pending:true}));
 w.eval(base);if(!soloMenu)w.eval(fuente);await tick();
 const el=i=>w.document.getElementById(i);
 const responder=async(i,data,status=200)=>{assert.ok(requests[i],'Solicitud '+i);requests[i].pending=false;requests[i].resolve({ok:status>=200&&status<300,status,json:async()=>data});await tick();await tick();};
 const pendiente=recurso=>requests.findLastIndex(r=>r.pending&&r.url.pathname==='/api/v1/alertas-sms/'+recurso+'/');
 const recibir=async(recurso,data,status=200)=>{const i=pendiente(recurso);assert.notEqual(i,-1,'Consulta pendiente: '+recurso);await responder(i,data,status);return i;};
 const campo=(i,v,evento='change')=>{el(i).value=v;el(i).dispatchEvent(new w.Event(evento));};
 const debounces=async(delay=300)=>{for(const[i,t]of [...timers])if(t.delay===delay){timers.delete(i);t.fn();}await tick();};
 const posts=()=>requests.filter(r=>r.options.method==='POST'&&r.url.pathname.includes('alertas-sms'));
 const iniciar=async({config={},historial=pagina()}={})=>{await recibir('acceso',{data:{ver:true,procesar:true}});await recibir('opciones',opciones());await recibir('estado',servicio(config));await recibir('historial',historial);};
 const preparar=async(envios=[aviso()])=>{el('prepararSMS').click();await recibir('preparar',{data:{envios,lote_maximo:3,cuota_disponible:8}});};
 return{w,el,requests,responder,recibir,pendiente,campo,debounces,posts,iniciar,preparar};
}

test('consulta inicial y permisos comparten una lectura y no envían SMS',async t=>{
 const c=await pantalla(t);assert.equal(c.requests.length,1);await c.iniciar();
 assert.equal(c.el('menu-sms').hidden,false);assert.equal(c.el('panelSMS').hidden,false);assert.equal(c.el('prepararSMS').disabled,false);assert.match(c.el('filasSMS').textContent,/Martillo 1/);assert.equal(c.posts().length,0);
 assert.equal(c.requests.find(r=>r.url.pathname.endsWith('/historial/')).url.searchParams.get('estado'),'PENDIENTE');
});
test('un rol local de administrador no concede acceso si el servidor lo rechaza',async t=>{
 const c=await pantalla(t);await c.recibir('acceso',{data:{ver:false,procesar:false}});
 assert.equal(c.requests.length,1);assert.equal(c.el('menu-sms').hidden,true);assert.equal(c.el('panelSMS').hidden,true);assert.match(c.el('errorSMS').textContent,/Solo los administradores/);
});
test('servicio pausado, cuota agotada y configuración incompleta conservan la consulta',async t=>{
 for(const [config,mensaje]of [[{activa:false},/pausados/],[{cuota_disponible:0},/límite diario/],[{configurada:false,errores_configuracion:['Falta remitente']},/configuración/]]){
  const c=await pantalla(t);await c.iniciar({config});assert.equal(c.el('prepararSMS').disabled,true);assert.match(c.el('ayudaProcesarSMS').textContent,mensaje);assert.equal(c.el('filasSMS').querySelectorAll('[data-detalle]').length,1);assert.equal(c.posts().length,0);
 }
});
test('en móvil los filtros empiezan resumidos y la zona horaria queda visible',async t=>{
 const c=await pantalla(t,{mobile:true});await c.iniciar();assert.equal(c.el('detalleFiltrosSMS').open,false);assert.match(c.el('resumenFiltrosSMS').textContent,/Pendiente/);assert.match(c.el('zonaSMS').textContent,/America\/Santiago/);
});
test('preparar usa los filtros vigentes y requiere confirmar los mismos identificadores',async t=>{
 const c=await pantalla(t);await c.iniciar();c.campo('bodegaSMS','2');await c.recibir('historial',pagina([aviso(2,{bodega:'Bodega Norte'})]));
 const envios=[aviso(2,{bodega:'Bodega Norte'}),aviso(3,{bodega:'Bodega Norte'})];await c.preparar(envios);
 assert.equal(c.requests.findLast(r=>r.url.pathname.endsWith('/preparar/')).url.searchParams.get('bodega'),'2');assert.equal(c.posts().length,0);assert.match(c.el('ayudaModalSMS').textContent,/saldo de Twilio/);
 c.el('confirmarModalSMS').click();c.el('confirmarModalSMS').click();assert.equal(c.posts().length,1);assert.deepEqual(JSON.parse(c.posts()[0].options.body),{ids:[id(2),id(3)]});assert.equal(c.el('cerrarModalSMS').disabled,true);
 await c.recibir('procesar-pendientes',{success:true,mensaje:'Aceptado todavía no significa entregado.',data:{revisados:2,resultados:envios.map(e=>({...e,estado:'ACEPTADO',estado_etiqueta:etiquetas.ACEPTADO,procesable:false,cancelable:false}))}});
 await c.recibir('estado',servicio());await c.recibir('historial',pagina());assert.equal(c.el('confirmarModalSMS').hidden,true);assert.match(c.el('contenidoModalSMS').textContent,/Aceptado por Twilio/);assert.equal(c.posts().length,1);
});
test('una vista previa que llega después de cambiar filtros no permite procesar',async t=>{
 const c=await pantalla(t);await c.iniciar();c.el('prepararSMS').click();c.campo('bodegaSMS','2');await c.recibir('preparar',{data:{envios:[aviso()]}});
 assert.match(c.el('errorModalSMS').textContent,/filtros cambiaron/);assert.equal(c.el('confirmarModalSMS').hidden,true);assert.equal(c.posts().length,0);
});
test('cambiar filtros después de preparar también bloquea la confirmación',async t=>{
 const c=await pantalla(t);await c.iniciar();await c.preparar();c.campo('buscarSMS','Sierra','input');c.el('confirmarModalSMS').click();
 assert.match(c.el('errorModalSMS').textContent,/filtros cambiaron/);assert.equal(c.posts().length,0);
});
test('un resultado incierto de red nunca repite el POST; solo ofrece consultar el historial',async t=>{
 const c=await pantalla(t);await c.iniciar();await c.preparar();c.el('confirmarModalSMS').click();c.posts()[0].reject(new Error('Conexión cerrada'));await tick();await tick();
 assert.equal(c.el('confirmarModalSMS').hidden,true);assert.match(c.el('errorModalSMS').textContent,/confirmar el resultado/);assert.match(c.el('ayudaModalSMS').textContent,/estado previo/);
 c.el('consultarResultadoSMS').click();assert.equal(c.posts().length,1);assert.notEqual(c.pendiente('historial'),-1);assert.notEqual(c.pendiente('estado'),-1);
});
test('un error 503 o JSON ilegible tras procesar exige comprobar el resultado',async t=>{
 for(const jsonRoto of [false,true]){
  const c=await pantalla(t);await c.iniciar();await c.preparar();c.el('confirmarModalSMS').click();
  if(jsonRoto){c.posts()[0].resolve({ok:true,status:200,json:async()=>{throw new Error('JSON inválido');}});await tick();await tick();}else await c.recibir('procesar-pendientes',{detail:'Error temporal'},503);
  assert.equal(c.el('confirmarModalSMS').hidden,true);assert.equal(c.el('consultarResultadoSMS').hidden,false);assert.match(c.el('ayudaModalSMS').textContent,/estado previo/);assert.equal(c.posts().length,1);
 }
});
test('cancelar requiere confirmación y solo afecta el identificador consultado',async t=>{
 const c=await pantalla(t);await c.iniciar();c.el('filasSMS').querySelector('[data-detalle]').click();await c.recibir('historial/'+id(1),{data:aviso()});assert.equal(c.posts().length,0);
 c.el('cancelarAvisoSMS').click();assert.match(c.el('ayudaModalSMS').textContent,/stock se conservan/);assert.equal(c.posts().length,0);c.el('confirmarModalSMS').click();c.el('confirmarModalSMS').click();
 assert.equal(c.posts().length,1);assert.match(c.posts()[0].url.pathname,new RegExp(id(1)+'/cancelar/$'));assert.deepEqual(JSON.parse(c.posts()[0].options.body),{});
 await c.recibir('historial/'+id(1)+'/cancelar',{success:true});await c.recibir('estado',servicio());await c.recibir('historial',pagina([]));assert.match(c.el('contenidoModalSMS').textContent,/Cancelado/);
});
test('detalles inciertos o entregados no ofrecen procesar ni cancelar',async t=>{
 for(const estado of ['INCIERTO','ENVIANDO','ENTREGADO','ACEPTADO']){
  const c=await pantalla(t);await c.iniciar();c.el('filasSMS').querySelector('[data-detalle]').click();await c.recibir('historial/'+id(1),{data:aviso(1,{estado,estado_etiqueta:etiquetas[estado],procesable:false,cancelable:false,motivo:'Revisa el estado del proveedor.'})});
  assert.equal(c.el('procesarAvisoSMS').hidden,true);assert.equal(c.el('cancelarAvisoSMS').hidden,true);assert.equal(c.el('confirmarModalSMS').hidden,true);assert.equal(c.posts().length,0);
 }
});
test('procesar un aviso vuelve a consultar su estado antes de mostrar confirmación',async t=>{
 const c=await pantalla(t);await c.iniciar();c.el('filasSMS').querySelector('[data-detalle]').click();await c.recibir('historial/'+id(1),{data:aviso()});c.el('procesarAvisoSMS').click();
 assert.equal(c.posts().length,0);await c.recibir('historial/'+id(1),{data:aviso(1,{procesable:false,motivo:'Esperando el siguiente intento.'})});assert.equal(c.el('confirmarModalSMS').hidden,true);assert.equal(c.el('procesarAvisoSMS').disabled,true);
});
test('rechazo de cuota conserva diagnóstico y no permite repetir la mutación',async t=>{
 const c=await pantalla(t);await c.iniciar();await c.preparar();c.el('confirmarModalSMS').click();await c.recibir('procesar-pendientes',{mensaje:'Se alcanzó el límite diario.'},409);
 assert.match(c.el('errorModalSMS').textContent,/límite diario/);assert.equal(c.el('confirmarModalSMS').hidden,true);assert.equal(c.el('consultarResultadoSMS').hidden,false);assert.equal(c.posts().length,1);
});
test('búsqueda descarta resultados atrasados y fechas invertidas evitan consultas',async t=>{
 const c=await pantalla(t);await c.iniciar();c.campo('buscarSMS','Sierra','input');await c.debounces();const antigua=c.pendiente('historial');c.campo('buscarSMS','Taladro','input');await c.debounces();await c.responder(antigua,pagina([aviso(2,{producto:'VIEJO'})]));assert.doesNotMatch(c.el('filasSMS').textContent,/VIEJO/);
 await c.recibir('historial',pagina([aviso(3,{producto:'Taladro'})]));assert.match(c.el('filasSMS').textContent,/Taladro/);c.campo('desdeSMS','2026-11-03');await c.recibir('historial',pagina());const antes=c.requests.length;c.campo('hastaSMS','2026-11-02');assert.equal(c.requests.length,antes);assert.match(c.el('errorListaSMS').textContent,/fecha inicial/);assert.equal(c.el('prepararSMS').disabled,true);
});
test('paginación recupera la última página si la cola se redujo',async t=>{
 const c=await pantalla(t);await c.iniciar({historial:pagina([aviso()],55,10)});c.el('paginasSMS').querySelector('[data-page="3"]').click();await c.recibir('historial',{detail:'No existe'},404);assert.equal(c.requests.at(-1).url.searchParams.get('page'),'last');await c.recibir('historial',pagina([aviso()],26,10));assert.match(c.el('conteoSMS').textContent,/26–26 de 26/);
});
test('textos de mensajes, productos y errores no interpretan HTML',async t=>{
 const malicioso=aviso(1,{producto:'<img src=x onerror=alert(1)>',detalle:'<b>Error</b>',mensaje:'<script>alert(1)</script>\nMensaje'});const c=await pantalla(t);await c.iniciar({historial:pagina([malicioso])});assert.equal(c.el('filasSMS').querySelector('img,b,script'),null);
 c.el('filasSMS').querySelector('[data-detalle]').click();await c.recibir('historial/'+id(1),{data:malicioso});assert.equal(c.el('contenidoModalSMS').querySelector('img,b,script'),null);assert.match(c.el('contenidoModalSMS').textContent,/<script>/);
});
test('sesión vencida comparte renovación y conserva tema y token rotado',async t=>{
 const c=await pantalla(t);await c.recibir('acceso',{},401);assert.equal(c.requests.filter(r=>r.url.pathname.endsWith('/auth/refresh/')).length,1);await c.responder(c.requests.length-1,{data:{access:'nuevo',refresh:'rotado'}});assert.equal(c.requests.at(-1).options.headers.Authorization,'Bearer nuevo');await c.recibir('acceso',{data:{ver:true,procesar:true}});await c.recibir('opciones',opciones());
 const a=c.pendiente('estado'),b=c.pendiente('historial');await c.responder(a,{},401);await c.responder(b,{},401);assert.equal(c.requests.filter(r=>r.pending&&r.url.pathname.endsWith('/auth/refresh/')).length,1);await c.responder(c.requests.length-1,{access:'nuevo2'});await c.recibir('estado',servicio());await c.recibir('historial',pagina());assert.equal(c.w.localStorage.getItem('smartstock-theme'),'dark');assert.equal(c.w.localStorage.getItem('refresh_token'),'rotado');
});
test('el menú de otras pantallas espera la renovación principal sin competir por el refresh',async t=>{
 const c=await pantalla(t,{soloMenu:true});await c.recibir('acceso',{},401);assert.equal(c.requests.filter(r=>r.options.method==='POST').length,0);c.w.localStorage.setItem('access_token','renovado-por-catalogo');await c.debounces(1000);assert.equal(c.requests.at(-1).options.headers.Authorization,'Bearer renovado-por-catalogo');await c.recibir('acceso',{data:{ver:true,procesar:true}});assert.equal(c.el('menu-sms').hidden,false);
});
test('datos de historial inválidos bloquean la preparación y ofrecen reintentar',async t=>{
 const c=await pantalla(t);await c.iniciar({historial:{count:1,revisables:1,results:[{id:'no-es-uuid'}]}});assert.equal(c.el('prepararSMS').disabled,true);assert.equal(c.el('reintentarListaSMS').hidden,false);assert.match(c.el('errorListaSMS').textContent,/formato inválido/);
});

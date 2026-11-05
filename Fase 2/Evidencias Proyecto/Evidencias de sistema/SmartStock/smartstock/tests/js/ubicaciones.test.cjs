const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../..');
const nuevo=readFileSync(path.join(root,'templates/ubicaciones.html'),'utf8');
let html=readFileSync(path.join(root,'templates/bodegas.html'),'utf8');
for(const bloque of ['bodega_contenido','bodega_modales']){
 const patron=new RegExp('{% block '+bloque+' %}([\\s\\S]*?){% endblock %}');
 html=html.replace(patron,nuevo.match(patron)[1]);
}
html=html.replace(/{%[\s\S]*?%}/g,'');
const fuente=readFileSync(path.join(root,'static/js/ubicaciones.js'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const opciones=(gestionar=true)=>({data:{permisos:{ver:true,gestionar},menu:{auditoria:true,usuarios:true,configuracion:true},bodegas:[{id:1,nombre:'Bodega Central',activa:true},{id:2,nombre:'Bodega Norte',activa:true},{id:3,nombre:'Antigua',activa:false}]}});
const pagina=(results=[],count=results.length)=>({results,count});
const referencia=(extra={})=>({id:8,producto_id:5,producto:'Martillo',sku:'P-5',activo:true,ubicacion_id:40,cantidad_heredada:0,ruta:{pasillo:'A',estanteria:'E1',nivel:'N1',ubicacion:'U1'},...extra});
async function pantalla(t,{query='',mobile=false}={}){
 const dom=new JSDOM(html,{url:'http://localhost/ubicaciones/'+query,runScripts:'outside-only',pretendToBeVisual:true});t.after(()=>dom.window.close());
 const w=dom.window,requests=[],timers=new Map();let numero=0;
 w.localStorage.setItem('access_token','inicial');w.localStorage.setItem('refresh_token','renovar');w.localStorage.setItem('smartstock-theme','dark');w.localStorage.setItem('usuario',JSON.stringify({nombre_completo:'Persona Prueba',rol_nombre:'Encargado'}));
 w.smartstockClearSession=()=>{};w.HTMLElement.prototype.scrollIntoView=()=>{};
 const listeners=[];const media={matches:mobile,addEventListener:(_tipo,fn)=>listeners.push(fn)};w.matchMedia=()=>media;
 const cambiarVista=valor=>{media.matches=valor;listeners.forEach(fn=>fn({matches:valor}));};
 w.bootstrap={Modal:class{constructor(n){this.n=n;}show(){this.n.classList.add('show');this.n.dispatchEvent(new w.Event('shown.bs.modal'));}hide(){const e=new w.Event('hide.bs.modal',{cancelable:true});this.n.dispatchEvent(e);if(!e.defaultPrevented){this.n.classList.remove('show');this.n.dispatchEvent(new w.Event('hidden.bs.modal'));}}}};
 w.setTimeout=(fn,delay)=>{timers.set(++numero,{fn,delay});return numero;};w.clearTimeout=id=>timers.delete(id);
 w.fetch=(url,options={})=>new Promise((resolve,reject)=>requests.push({url:new URL(url,w.location.href),options,resolve,reject,pending:true}));
 w.eval(fuente);await tick();
 const el=id=>w.document.getElementById(id);
 const responder=async(i,data,status=200)=>{requests[i].pending=false;requests[i].resolve({ok:status>=200&&status<300,status,json:async()=>data});await tick();await tick();};
 const pendiente=recurso=>requests.findLastIndex(r=>r.pending&&r.url.pathname==='/api/v1/ubicaciones/'+recurso+'/');
 const recibir=async(recurso,data,status=200)=>{const n=pendiente(recurso);assert.notEqual(n,-1,'Solicitud pendiente: '+recurso);await responder(n,data,status);return n;};
 const campo=(id,value,evento='change')=>{el(id).value=value;el(id).dispatchEvent(new w.Event(evento));};
 const enviar=id=>el(id).dispatchEvent(new w.Event('submit',{cancelable:true}));
 const debounces=async()=>{for(const[id,timer]of [...timers])if(timer.delay===300){timers.delete(id);timer.fn();}await tick();};
 async function cadena(bodega=1,pasillos=1){
  await recibir('pasillos',pagina([{id:10,codigo:'A',padre_id:bodega,elementos:1}],pasillos));
  await recibir('estanterias',pagina([{id:20,codigo:'E1',padre_id:10,elementos:1}]));
  await recibir('niveles',pagina([{id:30,codigo:'N1',padre_id:20,elementos:1}]));
  await recibir('espacios',pagina([{id:40,codigo:'U1',padre_id:30,elementos:0}]));
 }
 async function iniciar({gestionar=true,asignaciones=pagina([referencia()]),bodega=1,producto,pasillos=1}={}){
  await responder(0,opciones(gestionar));
  if(producto)await recibir('productos',pagina([producto]));
  await recibir('asignaciones',asignaciones);await cadena(bodega,pasillos);
 }
 return{w,el,requests,responder,recibir,pendiente,campo,enviar,debounces,cadena,iniciar,cambiarVista};
}

test('estructura encadenada y referencias iniciales corresponden a la bodega',async t=>{
 const c=await pantalla(t);await c.iniciar();
 assert.match(c.el('rutaUbicaciones').textContent,/Bodega Central \/ A \/ E1 \/ N1 \/ U1/);
 assert.equal(c.el('asignarProductoUbicacion').disabled,false);assert.match(c.el('filasAsignaciones').textContent,/Martillo/);
 assert.equal(c.requests.find(r=>r.url.pathname.endsWith('/estanterias/')).url.searchParams.get('pasillo'),'10');
});

test('sin permisos no carga ni expone la estructura',async t=>{
 const c=await pantalla(t);await c.responder(0,{data:{permisos:{ver:false,gestionar:false},bodegas:[]}});
 assert.equal(c.requests.length,1);assert.equal(c.el('panelUbicaciones').hidden,true);assert.match(c.el('errorUbicaciones').textContent,/No tienes permiso/);
});

test('lector e instalaciones inactivas permiten consultar sin acciones de escritura',async t=>{
 for(const ajuste of [{gestionar:false,bodega:1},{gestionar:true,bodega:3}]){
  const c=await pantalla(t,{query:'?bodega='+ajuste.bodega});await c.iniciar(ajuste);
  assert.equal(c.el('asignarProductoUbicacion').hidden,true);assert.equal(c.w.document.querySelector('[data-nuevo="pasillos"]').hidden,true);
  assert.equal(c.el('filasAsignaciones').querySelector('[data-retirar]'),null);
 }
});

test('bodega inexistente del enlace no cambia silenciosamente a Central',async t=>{
 const c=await pantalla(t,{query:'?bodega=999'});await c.responder(0,opciones());
 assert.equal(c.requests.length,1);assert.match(c.el('errorUbicaciones').textContent,/bodega solicitada/);assert.equal(c.el('panelUbicaciones').hidden,true);
});

test('cambiar bodega invalida estructura y respuestas atrasadas',async t=>{
 const c=await pantalla(t);await c.responder(0,opciones());const antigua=c.pendiente('pasillos');
 c.campo('bodegaUbicaciones','2');const nueva=c.pendiente('pasillos');
 await c.responder(antigua,pagina([{id:99,codigo:'ANTIGUA',padre_id:1}]));assert.doesNotMatch(c.el('elegir-pasillos').textContent,/ANTIGUA/);
 await c.responder(nueva,pagina([{id:12,codigo:'NORTE',padre_id:2}]));assert.equal(c.el('elegir-pasillos').value,'12');
 assert.equal(c.requests.at(-1).url.searchParams.get('bodega'),'2');assert.equal(c.w.location.search,'?bodega=2');
});

test('buscar estructura desactiva hijos y descarta las selecciones anteriores',async t=>{
 const c=await pantalla(t);await c.iniciar();c.campo('buscar-pasillos','B','input');
 assert.equal(c.el('elegir-estanterias').disabled,true);assert.equal(c.el('asignarProductoUbicacion').disabled,true);
 await c.debounces();assert.equal(c.requests.at(-1).url.searchParams.get('search'),'B');
 await c.recibir('pasillos',pagina());assert.equal(c.w.document.querySelector('[data-nuevo="pasillos"]').disabled,false);assert.equal(c.w.document.querySelector('[data-nuevo="estanterias"]').disabled,true);
});

test('error de estructura permite reintento y conserva el contexto',async t=>{
 const c=await pantalla(t);await c.responder(0,opciones());await c.recibir('pasillos',{detail:'No disponible'},503);
 assert.equal(c.el('reintentar-pasillos').hidden,false);c.el('reintentar-pasillos').click();assert.equal(c.requests.at(-1).url.searchParams.get('bodega'),'1');
});

test('crear un nivel envía su padre y bloquea envíos duplicados',async t=>{
 const c=await pantalla(t);await c.iniciar();let avisos=0;c.w.addEventListener('smartstock:notifications-changed',()=>avisos++);c.w.document.querySelector('[data-nuevo="niveles"]').click();c.el('codigoUbicacion').value='N2';c.enviar('formCodigoUbicacion');c.enviar('formCodigoUbicacion');
 const altas=c.requests.filter(r=>r.options.method==='POST');assert.equal(altas.length,1);assert.deepEqual(JSON.parse(altas[0].options.body),{codigo:'N2',estanteria:20});
 assert.equal(c.el('guardarCodigoUbicacion').disabled,true);
 await c.responder(c.requests.indexOf(altas[0]),{data:{id:31,codigo:'N2'}},201);
 assert.equal(avisos,1);
 assert.equal(c.el('modalCodigoUbicacion').classList.contains('show'),false);
 await c.recibir('niveles',pagina([{id:31,codigo:'N2',padre_id:20,elementos:0}]));
 assert.equal(c.el('elegir-niveles').value,'31');assert.equal(c.el('buscador-niveles').hidden,true);
});

test('editar un código no envía un cambio de padre',async t=>{
 const c=await pantalla(t);await c.iniciar();c.w.document.querySelector('[data-editar="estanterias"]').click();c.el('codigoUbicacion').value='E2';c.enviar('formCodigoUbicacion');
 assert.match(c.requests.at(-1).url.pathname,/estanterias\/20\/$/);assert.equal(c.requests.at(-1).options.method,'PATCH');assert.deepEqual(JSON.parse(c.requests.at(-1).options.body),{codigo:'E2'});
});

test('borrado rechazado mantiene el diálogo y la estructura visible',async t=>{
 const c=await pantalla(t);await c.iniciar();c.w.document.querySelector('[data-eliminar="pasillos"]').click();c.enviar('formRetirarUbicacion');
 await c.responder(c.requests.length-1,{mensaje:'Contiene estanterías'},409);
 assert.equal(c.el('modalRetirarUbicacion').classList.contains('show'),true);assert.match(c.el('errorRetirarUbicacion').textContent,/estanterías/);assert.equal(c.el('elegir-pasillos').value,'10');
});

test('producto del catálogo filtra referencias y prepara la asignación sin cargar todo el catálogo',async t=>{
 const c=await pantalla(t,{query:'?bodega=1&producto=5'});await c.iniciar({producto:{id:5,nombre:'Martillo',sku:'P-5',activo:true}});
 assert.match(c.el('contextoProducto').textContent,/Martillo/);assert.equal(c.requests.find(r=>r.url.pathname.endsWith('/asignaciones/')).url.searchParams.get('producto'),'5');
 c.el('asignarProductoUbicacion').click();await c.recibir('productos',pagina([{id:5,nombre:'Martillo',sku:'P-5',activo:true}]));
 assert.equal(c.el('productoAsignarUbicacion').value,'5');assert.equal(c.el('guardarAsignacionUbicacion').disabled,false);assert.equal(c.el('busquedaAsignarUbicacion').hidden,true);
 c.enviar('formAsignarUbicacion');assert.deepEqual(JSON.parse(c.requests.at(-1).options.body),{producto_id:5,ubicacion_id:40});
});

test('buscar productos invalida resultados anteriores y bloquea paginación durante el debounce',async t=>{
 const c=await pantalla(t);await c.iniciar();c.el('asignarProductoUbicacion').click();const vieja=c.pendiente('productos');
 c.campo('buscarProductoUbicacion','Sierra','input');await c.responder(vieja,pagina([{id:5,nombre:'VIEJO',sku:'X',activo:true}],80));
 assert.doesNotMatch(c.el('productoAsignarUbicacion').textContent,/VIEJO/);assert.equal(c.el('siguienteProductoUbicacion').disabled,true);assert.equal(c.el('guardarAsignacionUbicacion').disabled,true);
 await c.debounces();assert.equal(c.requests.at(-1).url.searchParams.get('search'),'Sierra');await c.recibir('productos',pagina([{id:6,nombre:'Sierra',sku:'S',activo:true}],30));
 c.campo('productoAsignarUbicacion','6');assert.equal(c.el('guardarAsignacionUbicacion').disabled,false);c.el('siguienteProductoUbicacion').click();assert.equal(c.requests.at(-1).url.searchParams.get('page'),'2');
});

test('referencias se buscan con paginación y recuperación de la última página',async t=>{
 const c=await pantalla(t);await c.iniciar({asignaciones:pagina([referencia()],55)});c.el('paginasAsignaciones').querySelector('[data-page="3"]').click();
 await c.recibir('asignaciones',{detail:'Página inexistente'},404);assert.equal(c.requests.at(-1).url.searchParams.get('page'),'last');
 await c.recibir('asignaciones',pagina([referencia()]));assert.match(c.el('resumenAsignaciones').textContent,/1–1 de 1/);
 c.el('soloUbicacion').checked=true;c.el('soloUbicacion').dispatchEvent(new c.w.Event('change'));assert.equal(c.requests.at(-1).url.searchParams.get('ubicacion'),'40');
});

test('paginar la estructura retira el filtro de una ubicación que dejó de estar seleccionada',async t=>{
 const c=await pantalla(t);await c.iniciar({pasillos:30});c.el('soloUbicacion').checked=true;c.el('soloUbicacion').dispatchEvent(new c.w.Event('change'));await c.recibir('asignaciones',pagina([referencia()]));
 c.el('siguiente-pasillos').click();assert.equal(c.el('soloUbicacion').checked,false);assert.equal(c.el('soloUbicacion').disabled,true);assert.equal(c.requests[c.pendiente('asignaciones')].url.searchParams.has('ubicacion'),false);assert.match(c.el('filasAsignaciones').textContent,/Cargando/);
});

test('cantidades heredadas se muestran sin permitir retirar unidades por esta pantalla',async t=>{
 const c=await pantalla(t);await c.iniciar({asignaciones:pagina([referencia({cantidad_heredada:4})])});assert.match(c.el('filasAsignaciones').textContent,/Cantidad heredada: 4/);assert.equal(c.el('filasAsignaciones').querySelector('[data-retirar]').disabled,true);
});

test('retirar referencia confirma destino y conserva la intención al fallar la red',async t=>{
 const c=await pantalla(t);await c.iniciar();c.el('filasAsignaciones').querySelector('[data-retirar]').click();assert.match(c.el('descripcionRetirarUbicacion').textContent,/stock se conserva/);
 c.enviar('formRetirarUbicacion');c.enviar('formRetirarUbicacion');const req=c.requests.at(-1);assert.equal(req.options.method,'DELETE');req.reject(new Error('Red cortada'));await tick();await tick();
 assert.match(c.el('errorRetirarUbicacion').textContent,/Revisa el listado/);assert.equal(c.el('modalRetirarUbicacion').classList.contains('show'),true);assert.equal(c.requests.filter(r=>r.options.method==='DELETE').length,1);
});

test('textos de productos y ubicaciones se renderizan sin interpretar HTML',async t=>{
 const c=await pantalla(t);await c.iniciar({asignaciones:pagina([referencia({producto:'<img src=x onerror=alert(1)>',ruta:{pasillo:'<b>A</b>',estanteria:'E1',nivel:'N1',ubicacion:'U1'}})])});
 assert.equal(c.el('filasAsignaciones').querySelector('img,b'),null);assert.match(c.el('filasAsignaciones').textContent,/<img/);
});

test('renovación JWT reintenta sin borrar el tema ni filtros',async t=>{
 const c=await pantalla(t);await c.responder(0,{},401);assert.equal(c.requests[1].url.pathname,'/api/v1/auth/refresh/');await c.responder(1,{data:{access:'nuevo',refresh:'rotado'}});
 assert.equal(c.requests[2].options.headers.Authorization,'Bearer nuevo');await c.responder(2,{data:{permisos:{ver:false,gestionar:false},bodegas:[]}});
 assert.equal(c.w.localStorage.getItem('smartstock-theme'),'dark');assert.equal(c.w.localStorage.getItem('refresh_token'),'rotado');
});

test('celular resume los pasos elegidos y mantiene la selección al desplegar o cambiar de ancho',async t=>{
 const c=await pantalla(t,{mobile:true});await c.iniciar();
 assert.deepEqual([...c.w.document.querySelectorAll('.ss-location-step[open]')].map(n=>n.id),['paso-espacios']);
 assert.equal(c.el('seleccion-pasillos').textContent,'A');assert.equal(c.el('seleccion-estanterias').textContent,'E1');
 const antes=c.requests.length;c.el('resumen-pasillos').click();assert.equal(c.el('paso-pasillos').open,true);assert.equal(c.el('paso-espacios').open,false);assert.equal(c.requests.length,antes);
 c.cambiarVista(false);assert.equal(c.w.document.querySelectorAll('.ss-location-step[open]').length,4);
 c.cambiarVista(true);assert.equal(c.el('paso-pasillos').open,true);assert.equal(c.el('elegir-espacios').value,'40');assert.equal(c.el('asignarProductoUbicacion').disabled,false);
});

test('listas pequeñas ocultan buscador y paginación; un filtro activo sigue disponible para corregirlo',async t=>{
 const c=await pantalla(t,{mobile:true});await c.iniciar({pasillos:30});
 assert.equal(c.el('buscador-pasillos').hidden,false);assert.equal(c.el('paginas-pasillos').hidden,false);assert.equal(c.el('buscador-niveles').hidden,true);assert.equal(c.el('paginas-niveles').hidden,true);
 c.el('resumen-pasillos').click();c.campo('buscar-pasillos','XYZ','input');await c.debounces();await c.recibir('pasillos',pagina());
 assert.equal(c.el('buscador-pasillos').hidden,false);assert.equal(c.el('paginas-pasillos').hidden,true);assert.equal(c.el('paso-pasillos').open,true);assert.match(c.el('estado-pasillos').textContent,/coincidan/);
 c.campo('buscar-pasillos','','input');await c.debounces();await c.recibir('pasillos',pagina([{id:10,codigo:'A',padre_id:1}],30));assert.equal(c.el('paginas-pasillos').hidden,false);
});

test('un nivel vacío explica cómo habilitar la asignación y mantiene visible la creación',async t=>{
 const c=await pantalla(t,{mobile:true});await c.responder(0,opciones());await c.recibir('asignaciones',pagina());
 await c.recibir('pasillos',pagina([{id:10,codigo:'A',padre_id:1}]));await c.recibir('estanterias',pagina([{id:20,codigo:'E1',padre_id:10}]));await c.recibir('niveles',pagina([{id:30,codigo:'N1',padre_id:20}]));await c.recibir('espacios',pagina());
 assert.equal(c.el('paso-espacios').open,true);assert.match(c.el('estado-espacios').textContent,/nivel aún no tiene ubicaciones/);assert.match(c.el('rutaUbicaciones').textContent,/Crea una ubicación/);
 assert.equal(c.el('asignarProductoUbicacion').disabled,true);assert.equal(c.el('administrar-espacios').hidden,true);const crear=c.w.document.querySelector('[data-nuevo="espacios"]');assert.equal(crear.disabled,false);assert.match(crear.textContent,/Crear ubicación/);
 crear.click();assert.equal(c.el('modalCodigoUbicacion').classList.contains('show'),true);
});

test('un error de carga conserva su diagnóstico aunque el paginador esté oculto',async t=>{
 const c=await pantalla(t,{mobile:true});await c.responder(0,opciones());await c.recibir('pasillos',{detail:'Error temporal de conexión'},503);
 assert.equal(c.el('paginas-pasillos').hidden,true);assert.equal(c.el('estado-pasillos').hidden,false);assert.match(c.el('estado-pasillos').textContent,/Error temporal/);assert.equal(c.el('reintentar-pasillos').hidden,false);
});

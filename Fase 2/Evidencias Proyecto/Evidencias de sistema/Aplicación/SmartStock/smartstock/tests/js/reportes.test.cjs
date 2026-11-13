const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../..');
const html=readFileSync(path.join(root,'templates/reportes.html'),'utf8').replace(/{%[\s\S]*?%}/g,'');
const base=readFileSync(path.join(root,'static/js/reportes_base.js'),'utf8');
const fuente=readFileSync(path.join(root,'static/js/reportes.js'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const bodegas=[{id:1,nombre:'Bodega Central',activa:true},{id:2,nombre:'Bodega Antigua',activa:false}];
const pagina=(count=55,extra={})=>({count,results:[{sku:'REP-1',producto:'Martillo',stock:13}],meta:{informe:'existencias',titulo:'Existencias actuales',columnas:[{campo:'sku',etiqueta:'SKU'},{campo:'producto',etiqueta:'Producto'},{campo:'stock',etiqueta:'Unidades',numero:true}],resumen:[{etiqueta:'Unidades',valor:78}],notas:['Estado actual.'],filtros:[['Bodega','Bodega Central']],generado:'2026-11-01T20:00:00-03:00',orden:'Producto A–Z',permisos:{ver:true,exportar:true}},...extra});

async function pantalla(t,{soloBase=false}={}){
 const dom=new JSDOM(soloBase?'<li id="menu-reportes" hidden></li>':html,{url:'http://localhost/reportes/',runScripts:'outside-only',pretendToBeVisual:true});
 t.after(()=>dom.window.close());
 const w=dom.window,requests=[],timers=new Map();let numero=0;
 w.localStorage.setItem('access_token','inicial');w.localStorage.setItem('refresh_token','renovar');w.localStorage.setItem('smartstock-theme','dark');
 w.localStorage.setItem('usuario',JSON.stringify({nombre_completo:'Persona Prueba',rol:'administrador'}));
 w.HTMLElement.prototype.scrollIntoView=()=>{};w.smartstockClearSession=()=>{};
 w.setTimeout=(fn,delay)=>{timers.set(++numero,{fn,delay});return numero;};w.clearTimeout=id=>timers.delete(id);
 w.fetch=(url,options)=>new Promise((resolve,reject)=>requests.push({url:new URL(url,w.location.href),options,resolve,reject}));
 const descargas=[];w.URL.createObjectURL=blob=>{descargas.push(blob);return 'blob:reporte';};w.URL.revokeObjectURL=()=>{};w.HTMLAnchorElement.prototype.click=function(){descargas.push(this.download);};
 w.eval(base);if(!soloBase)w.eval(fuente);await tick();
 const el=id=>w.document.getElementById(id);
 const responder=async(i,data,status=200,headers={})=>{requests[i].resolve({ok:status>=200&&status<300,status,headers:{get:key=>headers[key.toLowerCase()]||''},json:async()=>data,blob:async()=>new w.Blob(['CSV']),text:async()=>String(data)});await tick();await tick();};
 const campo=(id,value,evento='change')=>{el(id).value=value;el(id).dispatchEvent(new w.Event(evento));};
 const debounces=async(delay=300)=>{for(const[id,timer]of [...timers])if(timer.delay===delay){timers.delete(id);timer.fn();}await tick();};
 async function iniciar({exportar=true,ver=true,datos=pagina()}={}){
  await responder(0,{data:{ver,exportar}});if(!ver)return;
  await responder(1,{data:{bodegas,permisos:{ver,exportar}}});
  await responder(2,{...datos,meta:{...datos.meta,permisos:{ver,exportar}}});
 }
 return{w,el,requests,responder,campo,debounces,iniciar,descargas,timers};
}

test('consulta inicial por bodega, resumen global y campos actuales sin fechas',async t=>{
 const c=await pantalla(t);await c.iniciar();const p=c.requests[2].url.searchParams;
 assert.equal(p.get('bodega'),'1');assert.equal(p.get('informe'),'existencias');assert.equal(p.has('desde'),false);
 assert.match(c.el('resumenReporte').textContent,/78/);assert.equal(c.el('desdeReporte').disabled,true);assert.equal(c.el('exportarReporte').disabled,false);assert.equal(c.el('exportarReporte').hidden,false);
 assert.match(c.el('metadatosReporte').textContent,/Bodega Central/);
});

test('sin permiso la pantalla queda restringida y no consulta inventario',async t=>{
 const c=await pantalla(t);await c.iniciar({ver:false,exportar:false});
 assert.equal(c.requests.length,1);assert.equal(c.el('filtrosReportes').hidden,true);assert.equal(c.el('exportarReporte').disabled,true);assert.match(c.el('errorReportes').textContent,/No tienes permiso/);
});

test('lector puede consultar y paginar sin poder descargar ni imprimir',async t=>{
 const c=await pantalla(t);await c.iniciar({exportar:false});assert.equal(c.el('exportarReporte').hidden,true);assert.equal(c.el('imprimirReporte').hidden,true);
 c.el('paginasReporte').querySelector('[data-page="2"]').click();assert.equal(c.requests.at(-1).url.searchParams.get('page'),'2');
});

test('historial activa fechas y permite todas las bodegas; stock no conserva filtros históricos',async t=>{
 const c=await pantalla(t);await c.iniciar();c.campo('informeReporte','movimientos');await c.responder(3,pagina());
 c.campo('desdeReporte','2026-10-01');await c.responder(4,pagina());c.campo('bodegaReporte','');await c.responder(5,pagina());
 assert.equal(c.requests[5].url.searchParams.has('bodega'),false);assert.equal(c.requests[5].url.searchParams.get('desde'),'2026-10-01');
 c.campo('informeReporte','critico');assert.equal(c.requests.at(-1).url.searchParams.has('desde'),false);assert.equal(c.requests.at(-1).url.searchParams.get('bodega'),'1');
});

test('rango inválido muestra error y no solicita ni permite exportar',async t=>{
 const c=await pantalla(t);await c.iniciar();c.campo('informeReporte','mermas');await c.responder(3,pagina());
 c.el('desdeReporte').value='2026-10-30';c.el('hastaReporte').value='2026-10-01';const antes=c.requests.length;
 c.el('filtrosReportes').dispatchEvent(new c.w.Event('submit',{cancelable:true}));assert.equal(c.requests.length,antes);assert.match(c.el('errorReportes').textContent,/posterior/);assert.equal(c.el('exportarReporte').disabled,true);
});

test('cambio de filtro descarta respuesta anterior y bloquea exportación durante debounce',async t=>{
 const c=await pantalla(t);await c.iniciar();c.campo('estadoProductoReporte','todos');const vieja=c.requests.length-1;
 c.campo('buscarReporte','Tuerca','input');assert.equal(c.el('exportarReporte').disabled,true);
 await c.responder(vieja,pagina(1,{results:[{producto:'Respuesta vieja'}]}));assert.doesNotMatch(c.el('filasReporte').textContent,/Respuesta vieja/);
 await c.debounces();assert.equal(c.requests.at(-1).url.searchParams.get('search'),'Tuerca');assert.equal(c.requests.at(-1).url.searchParams.get('page'),'1');
});

test('Kardex pide producto y bodega, sin descargar el catálogo entero',async t=>{
 const c=await pantalla(t);await c.iniciar();c.campo('informeReporte','kardex');
 assert.equal(c.requests.at(-1).url.pathname, '/api/v1/reportes/productos/');assert.match(c.el('filasReporte').textContent,/Selecciona un producto/);
 await c.responder(3,{count:30,results:[{id:8,sku:'REP-8',nombre:'Inactivo',activo:false}]});assert.match(c.el('productoReporte').textContent,/inactivo/);
 c.campo('productoReporte','8');assert.equal(c.requests.at(-1).url.searchParams.get('producto'),'8');assert.equal(c.requests.at(-1).url.searchParams.has('search'),false);
});

test('búsqueda del Kardex invalida selección y descarta productos atrasados',async t=>{
 const c=await pantalla(t);await c.iniciar();c.campo('informeReporte','kardex');
 c.campo('buscarProductoReporte','Sierra','input');await c.responder(3,{count:1,results:[{id:8,sku:'VIEJO',nombre:'Anterior'}]});assert.doesNotMatch(c.el('productoReporte').textContent,/VIEJO/);
 await c.debounces();assert.equal(c.requests.at(-1).url.searchParams.get('search'),'Sierra');await c.responder(4,{count:1,results:[{id:9,sku:'SIER-1',nombre:'Sierra',activo:true}]});assert.equal(c.el('productoReporte').value,'');assert.equal(c.el('exportarReporte').disabled,true);
});

test('fallo de catálogo de Kardex ofrece reintento y conserva búsqueda',async t=>{
 const c=await pantalla(t);await c.iniciar();c.campo('informeReporte','kardex');c.requests[3].reject(new Error('sin red'));await tick();await tick();
 assert.equal(c.el('reintentarProductosReporte').hidden,false);c.el('reintentarProductosReporte').click();assert.equal(c.requests[4].url.pathname,'/api/v1/reportes/productos/');
});

test('selector del Kardex recupera la última página si se eliminaron productos',async t=>{
 const c=await pantalla(t);await c.iniciar();c.campo('informeReporte','kardex');await c.responder(3,{count:30,results:[{id:8,sku:'P-8',nombre:'Producto',activo:true}]});
 c.el('productosReporteSiguiente').click();await c.responder(4,{detail:'Página inexistente'},404);
 assert.equal(c.requests[5].url.searchParams.get('page'),'last');await c.responder(5,{count:1,results:[{id:8,sku:'P-8',nombre:'Producto',activo:true}]});
 assert.match(c.el('estadoProductosReporte').textContent,/Página 1 de 1/);assert.equal(c.el('productoReporte').disabled,false);
});

test('paginación conserva filtros y recupera última página eliminada',async t=>{
 const c=await pantalla(t);await c.iniciar();c.el('paginasReporte').querySelector('[data-page="3"]').click();await c.responder(3,{detail:'No existe'},404);
 assert.equal(c.requests[4].url.searchParams.get('page'),'last');await c.responder(4,pagina(1));assert.match(c.el('conteoReporte').textContent,/Mostrando 1–1 de 1/);
});

test('datos y errores se renderizan como texto, sin interpretar HTML',async t=>{
 const c=await pantalla(t);await c.iniciar({datos:pagina(1,{results:[{sku:'X',producto:'<img src=x onerror=alert(1)>',stock:1}]})});
 assert.equal(c.el('filasReporte').querySelector('img'),null);assert.match(c.el('filasReporte').textContent,/<img/);
 c.campo('estadoProductoReporte','todos');await c.responder(3,{detail:'<script>malo</script>'},400);assert.match(c.el('errorReportes').textContent,/<script>/);assert.equal(c.el('errorReportes').querySelector('script'),null);
});

test('CSV usa filtros aplicados sin page, bloquea doble envío y descarga todo el archivo',async t=>{
 const c=await pantalla(t);await c.iniciar();c.el('exportarReporte').click();c.el('exportarReporte').click();assert.equal(c.requests.length,4);
 assert.equal(c.requests[3].url.pathname,'/api/v1/reportes/exportar/');assert.equal(c.requests[3].url.searchParams.has('page'),false);assert.equal(c.requests[3].url.searchParams.get('bodega'),'1');
 await c.responder(3,'archivo',200,{'content-type':'text/csv; charset=utf-8'});assert.equal(c.descargas.length,2);assert.equal(c.el('exportarReporte').disabled,false);assert.match(c.el('estadoExportarReporte').textContent,/todos los resultados/);
});

test('una exportación atrasada no descarga datos de filtros que cambiaron',async t=>{
 const c=await pantalla(t);await c.iniciar();c.el('exportarReporte').click();c.campo('estadoProductoReporte','inactivos');
 await c.responder(3,'archivo',200,{'content-type':'text/csv'});assert.equal(c.descargas.length,0);assert.match(c.el('estadoExportarReporte').textContent,/filtros cambiaron/);
});

test('error o formato incorrecto permite reintentar exportación sin abrir impresión',async t=>{
 const c=await pantalla(t);await c.iniciar();c.el('imprimirReporte').click();await c.responder(3,'json',200,{'content-type':'application/json'});
 assert.equal(c.w.document.querySelector('iframe'),null);assert.equal(c.el('imprimirReporte').disabled,false);assert.match(c.el('estadoExportarReporte').textContent,/formato solicitado/);
 c.el('imprimirReporte').click();await c.responder(4,{detail:'Acota las fechas'},400);assert.match(c.el('estadoExportarReporte').textContent,/Acota las fechas/);
});

test('reporte incompleto no deja habilitada la descarga',async t=>{
 const c=await pantalla(t);await c.iniciar({datos:{count:1,results:[]}});assert.equal(c.el('exportarReporte').disabled,true);assert.match(c.el('errorReportes').textContent,/incompleto/);
});

test('el menú consulta permisos reales y no supone acceso por el rol local',async t=>{
 const c=await pantalla(t,{soloBase:true});await c.responder(0,{data:{ver:false,exportar:false}});assert.equal(c.el('menu-reportes').hidden,true);
});

test('el menú muestra Reportes a usuarios con el permiso de lectura',async t=>{
 const c=await pantalla(t,{soloBase:true});await c.responder(0,{data:{ver:true,exportar:false}});assert.equal(c.el('menu-reportes').hidden,false);
});

test('el menú de otros módulos espera su renovación y no compite por el refresh',async t=>{
 const c=await pantalla(t,{soloBase:true});await c.responder(0,{},401);assert.equal(c.requests.length,1);
 c.w.localStorage.setItem('access_token','renovado-por-otro-modulo');await c.debounces(1000);
 assert.equal(c.requests[1].url.pathname,'/api/v1/reportes/acceso/');assert.equal(c.requests[1].options.headers.Authorization,'Bearer renovado-por-otro-modulo');
 await c.responder(1,{data:{ver:true,exportar:false}});assert.equal(c.el('menu-reportes').hidden,false);
});

test('renovación JWT reintenta una vez sin borrar tema ni filtros',async t=>{
 const c=await pantalla(t);await c.responder(0,{},401);assert.equal(c.requests[1].url.pathname,'/api/v1/auth/refresh/');
 await c.responder(1,{data:{access:'nuevo',refresh:'renovado'}});assert.equal(c.requests[2].options.headers.Authorization,'Bearer nuevo');
 await c.responder(2,{data:{ver:false,exportar:false}});assert.equal(c.w.localStorage.getItem('smartstock-theme'),'dark');assert.equal(c.w.localStorage.getItem('refresh_token'),'renovado');
});

test('consulta de permisos simultánea comparte la misma solicitud',async t=>{
 const c=await pantalla(t,{soloBase:true});const a=c.w.SmartStockReportes.acceso(),b=c.w.SmartStockReportes.acceso();assert.equal(c.requests.length,1);
 await c.responder(0,{data:{ver:true,exportar:true}});await Promise.all([a,b]);
});

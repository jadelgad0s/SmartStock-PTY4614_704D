const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.resolve(__dirname, '../..');
const html = readFileSync(path.join(root,'templates/bodegas.html'),'utf8').replace(/{%[\s\S]*?%}/g,'');
const fuente = readFileSync(path.join(root,'static/js/bodegas.js'),'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const opciones = require('./bodegas-fixture.cjs');
const bodega = (id=1) => ({id,nombre:'Bodega '+id,direccion:'Calle '+id,unidades:24,activa:true});
const lista = (count=32,page=1) => ({count,results:Array.from({length:Math.max(0,Math.min(25,count-(page-1)*25))},(_,i)=>bodega(i+1+(page-1)*25))});
async function pantalla(t,{mobile=false}={}) {
    const dom = new JSDOM(html,{url:'http://localhost/bodegas/',runScripts:'outside-only',pretendToBeVisual:true});
    t.after(()=>dom.window.close()); const w=dom.window, requests=[], timers=new Map(), modales=new Map(); let timer=0;
    w.localStorage.setItem('access_token','test'); w.localStorage.setItem('usuario',JSON.stringify({nombre_completo:'Persona Prueba',rol_nombre:'Administrador'}));
    w.HTMLElement.prototype.scrollIntoView=()=>{};
    w.smartstockClearSession=()=>w.localStorage.clear();
    const listeners=[];const media={matches:mobile,addEventListener:(_tipo,fn)=>listeners.push(fn)};w.matchMedia=()=>media;
    const cambiarVista=valor=>{media.matches=valor;listeners.forEach(fn=>fn({matches:valor}));};
    w.bootstrap={Modal:{getOrCreateInstance(elemento){
        if(!modales.has(elemento))modales.set(elemento,{
            show(){elemento.classList.add('show');elemento.dispatchEvent(new w.Event('shown.bs.modal'));},
            hide(){if(!elemento.dispatchEvent(new w.Event('hide.bs.modal',{cancelable:true})))return;elemento.classList.remove('show');elemento.dispatchEvent(new w.Event('hidden.bs.modal'));},
        });return modales.get(elemento);
    }}};
    w.setTimeout=fn=>{timers.set(++timer,fn);return timer;}; w.clearTimeout=id=>timers.delete(id);
    w.fetch=(url,options)=>new Promise((resolve,reject)=>requests.push({url:new URL(url,w.location.href),options,resolve,reject}));
    let avisos=0;w.addEventListener('smartstock:notifications-changed',()=>avisos++);
    w.eval(fuente); await tick(); const el=id=>w.document.getElementById(id);
    const responder=async(i,data,status=200)=>{requests[i].resolve({ok:status>=200&&status<300,status,json:async()=>data});await tick();};
    const campo=(id,value,event='input')=>{el(id).value=value;el(id).dispatchEvent(new w.Event(event));};
    const enviar=id=>el(id).dispatchEvent(new w.Event('submit',{cancelable:true}));
    const cargar=async(d=opciones())=>{await responder(0,d);await responder(1,lista());};
    const debounce=async()=>{const callbacks=[...timers.values()];timers.clear();callbacks.forEach(fn=>fn());await tick();};
    return {w,el,requests,responder,campo,enviar,cargar,debounce,modales,avisos:()=>avisos,cambiarVista};
}

test('listado por páginas conserva estado y búsqueda',async t=>{
    const c=await pantalla(t);await c.cargar();
    c.campo('buscarBodegas','Norte');await c.debounce();await c.responder(2,lista());
    c.campo('estadoBodegas','true','change');await c.responder(3,lista());
    c.el('paginacionBodegas').querySelector('[data-page="2"]').click();
    const p=c.requests[4].url.searchParams;
    assert.equal(p.get('page'),'2');assert.equal(p.get('search'),'Norte');assert.equal(p.get('activa'),'true');
    await c.responder(4,lista(32,2));assert.match(c.el('resumenBodegas').textContent,/26–32 de 32/);
    c.el('limpiarBodegas').click();assert.equal(c.requests[5].url.searchParams.get('page'),'1');assert.equal(c.requests[5].url.searchParams.has('search'),false);
});

test('formulario y listado trabajan solo con bodegas y sus datos existentes',async t=>{
    const c=await pantalla(t);await c.cargar();c.el('nuevaEntidad').click();
    assert.equal(c.el('entidadNombre').value,'');assert.equal(c.el('entidadDireccion').value,'');
    assert.equal(c.el('encabezadoBodegas').querySelectorAll('th').length,5);
    assert.equal(c.el('formEntidad').querySelectorAll('select').length,0);
    assert.equal(c.w.document.querySelector('[role=tablist]'),null);
});

test('permisos del servidor muestran solo lectura y bloquean aperturas por evento',async t=>{
    const c=await pantalla(t),d=opciones();d.data.permisos={};await c.cargar(d);
    assert.equal(c.el('nuevaEntidad').hidden,true);assert.equal(c.el('listaBodegas').querySelector('button'),null);
    assert.match(c.el('listaBodegas').textContent,/Solo lectura/);
    c.el('nuevaEntidad').click();assert.equal(c.el('modalEntidad').classList.contains('show'),false);
});

test('nombre y dirección de bodega no se interpretan como HTML',async t=>{
    const c=await pantalla(t);await c.responder(0,opciones());
    await c.responder(1,{count:1,results:[{...bodega(),nombre:'<img src=x onerror=alert(1)>',direccion:'<script>malo</script>'}]});
    assert.equal(c.el('listaBodegas').querySelector('img,script'),null);assert.match(c.el('listaBodegas').textContent,/<img/);
});

test('crear bodega valida nombre, evita doble envío y conserva datos ante errores',async t=>{
    const c=await pantalla(t);await c.cargar();c.el('nuevaEntidad').click();
    c.enviar('formEntidad');assert.equal(c.requests.length,2);assert.ok(c.el('entidadNombre').classList.contains('is-invalid'));
    c.campo('entidadNombre','Bodega prueba');c.campo('entidadDireccion','Calle de prueba');c.enviar('formEntidad');c.enviar('formEntidad');
    assert.equal(c.requests.length,3);assert.deepEqual(JSON.parse(c.requests[2].options.body),{nombre:'Bodega prueba',direccion:'Calle de prueba'});
    c.modales.get(c.el('modalEntidad')).hide();assert.ok(c.el('modalEntidad').classList.contains('show'));
    await c.responder(2,{nombre:['Ya existe una bodega con este nombre.']},400);
    assert.equal(c.el('entidadNombre').value,'Bodega prueba');assert.equal(c.el('entidadDireccion').value,'Calle de prueba');
    assert.ok(c.el('entidadNombre').classList.contains('is-invalid'));assert.equal(c.el('guardarEntidad').disabled,false);
});

test('crear bodega cierra al confirmar y avisa a la campana una sola vez',async t=>{
    const c=await pantalla(t);await c.cargar();c.el('nuevaEntidad').click();c.campo('entidadNombre','Bodega nueva');c.enviar('formEntidad');
    assert.equal(c.requests[2].url.pathname,'/api/v1/bodegas/');assert.equal(c.requests[2].options.method,'POST');
    await c.responder(2,{success:true,data:{id:3}},201);assert.equal(c.el('modalEntidad').classList.contains('show'),false);
    c.enviar('formEntidad');assert.equal(c.requests.length,4);assert.equal(c.avisos(),1);
    await c.responder(3,opciones());assert.equal(c.requests[4].url.pathname,'/api/v1/bodegas/');
});

test('editar obtiene detalle fresco y permite reintentar sin guardar valores vacíos',async t=>{
    const c=await pantalla(t);await c.cargar();c.el('listaBodegas').querySelector('[data-accion="editar"]').click();
    assert.equal(c.el('guardarEntidad').disabled,true);c.enviar('formEntidad');assert.equal(c.requests.length,3);
    await c.responder(2,{mensaje:'Temporalmente no disponible'},503);assert.equal(c.el('guardarEntidad').disabled,true);
    c.el('reintentarEntidad').click();await c.responder(3,{...bodega(),nombre:'Nombre actualizado',direccion:'Dirección completa'});
    assert.equal(c.el('entidadNombre').value,'Nombre actualizado');assert.equal(c.el('entidadDireccion').value,'Dirección completa');
    c.campo('entidadNombre','Nombre corregido');c.enviar('formEntidad');
    assert.equal(c.requests[4].options.method,'PATCH');assert.equal(JSON.parse(c.requests[4].options.body).direccion,'Dirección completa');
});

test('cerrar una edición pendiente de lectura descarta su respuesta',async t=>{
    const c=await pantalla(t);await c.cargar();const botones=c.el('listaBodegas').querySelectorAll('[data-accion="editar"]');
    botones[0].click();c.modales.get(c.el('modalEntidad')).hide();botones[1].click();
    await c.responder(2,{...bodega(),nombre:'Respuesta vieja'});assert.equal(c.el('entidadNombre').value,'');
    await c.responder(3,bodega(2));assert.equal(c.el('entidadNombre').value,'Bodega 2');
});

test('desactivar requiere confirmación actual y mantiene abierto el rechazo por existencias',async t=>{
    const c=await pantalla(t);await c.cargar();c.el('listaBodegas').querySelector('[data-accion="desactivar"]').click();
    c.enviar('formEstadoEntidad');assert.equal(c.requests.length,3);await c.responder(2,bodega());
    assert.equal(c.el('nombreAccionEntidad').textContent,'Bodega 1');c.enviar('formEstadoEntidad');c.enviar('formEstadoEntidad');
    assert.equal(c.requests.length,4);assert.equal(c.requests[3].options.method,'DELETE');
    c.modales.get(c.el('modalEstadoEntidad')).hide();assert.ok(c.el('modalEstadoEntidad').classList.contains('show'));
    await c.responder(3,{mensaje:'La bodega tiene existencias.'},409);
    assert.match(c.el('errorEstadoEntidad').textContent,/existencias/);assert.ok(c.el('modalEstadoEntidad').classList.contains('show'));assert.equal(c.avisos(),0);
});

test('un estado que cambió en el servidor bloquea la confirmación',async t=>{
    const c=await pantalla(t);await c.cargar();c.el('listaBodegas').querySelector('[data-accion="desactivar"]').click();
    await c.responder(2,{...bodega(),activa:false});assert.equal(c.el('confirmarEstadoEntidad').disabled,true);
    c.enviar('formEstadoEntidad');assert.equal(c.requests.length,3);assert.match(c.el('errorEstadoEntidad').textContent,/estado cambió/);
});

test('opciones fallidas se recuperan y una página eliminada intenta last una vez',async t=>{
    const c=await pantalla(t);await c.responder(0,{mensaje:'No disponible'},503);
    assert.equal(c.el('reintentarBodegas').hidden,false);c.el('reintentarBodegas').click();await c.responder(1,opciones());await c.responder(2,lista());
    c.el('paginacionBodegas').querySelector('[data-page="2"]').click();await c.responder(3,{detail:'Página no existe'},404);
    assert.equal(c.requests[4].url.searchParams.get('page'),'last');await c.responder(4,{detail:'Página no existe'},404);
    assert.equal(c.requests.length,5);assert.equal(c.el('listaBodegas').getAttribute('aria-busy'),'false');assert.equal(c.el('reintentarBodegas').hidden,false);
});

test('respuesta anterior al debounce no repone un listado equivocado',async t=>{
    const c=await pantalla(t);await c.responder(0,opciones());c.campo('buscarBodegas','Sur');await c.responder(1,lista());
    assert.equal(c.el('listaBodegas').querySelectorAll('.ss-bodega-row').length,0);await c.debounce();await c.responder(2,{count:0,results:[]});assert.equal(c.el('resumenBodegas').textContent,'0 registros');
});

test('las acciones de estado pasan del menú de PC a la tarjeta móvil conservando su bodega',async t=>{
    const c=await pantalla(t);await c.cargar();const grupo=c.el('listaBodegas').querySelector('.ss-bodegas-actions');
    const estado=grupo.querySelector('[data-accion="desactivar"]');assert.ok(estado.closest('.ss-bodega-more'));assert.equal(grupo.querySelector('a').getAttribute('href'),'/ubicaciones/?bodega=1');
    c.cambiarVista(true);assert.equal(estado.parentNode,grupo);assert.equal(grupo.querySelector('.ss-bodega-more'),null);
    c.cambiarVista(false);assert.equal(grupo.querySelector('[data-accion="desactivar"]'),estado);assert.equal(grupo.querySelectorAll('[data-accion="desactivar"]').length,1);
    const mas=grupo.querySelector('summary');mas.click();assert.equal(estado.closest('details').open,true);estado.click();assert.equal(c.requests.at(-1).url.pathname,'/api/v1/bodegas/1/');
});

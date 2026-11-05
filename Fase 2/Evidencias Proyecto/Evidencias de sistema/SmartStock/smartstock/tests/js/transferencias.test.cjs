const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.resolve(__dirname, '../..');
const html = readFileSync(path.join(root,'templates/transferencias.html'),'utf8').replace(/{%[\s\S]*?%}/g,'');
const fuente = readFileSync(path.join(root,'static/js/transferencias.js'),'utf8');
const camara = readFileSync(path.join(root,'static/js/escaneo_camara.js'),'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const producto = (extra={}) => ({id:1,sku:'FER-001',nombre:'Taladro 500 W',stock_origen:24,stock_destino:6,bodega_origen_id:1,bodega_destino_id:2,...extra});
const opciones = (extra={}) => ({success:true,data:{bodegas:[{id:1,nombre:'Bodega Central'},{id:2,nombre:'Bodega Norte'},{id:3,nombre:'Bodega Sur'}],bodegas_historial:[{id:1,nombre:'Bodega Central'},{id:2,nombre:'Bodega Norte'},{id:3,nombre:'Bodega Sur'},{id:4,nombre:'Bodega Antigua',activa:false}],bodega_predeterminada:1,permisos:{registrar:true,auditoria:true,usuarios:true,configuracion:true},...extra}});
const transferencia = (extra={}) => ({id:1,fecha:'01/11/2026 10:30',estado:'COMPLETADA',usuario:'Persona Prueba',bodega_origen:{id:1,nombre:'Bodega Central'},bodega_destino:{id:2,nombre:'Bodega Norte'},detalles:[{producto_id:1,sku:'FER-001',producto:'Taladro 500 W',cantidad:6}],cantidad_total:6,stock:{origen_anterior:24,origen_posterior:18,destino_anterior:6,destino_posterior:12},movimientos:{salida:1,entrada:2},...extra});
const lista = (count=1,page=1) => ({count,results:Array.from({length:Math.max(0,Math.min(25,count-(page-1)*25))},(_,i)=>transferencia({id:(page-1)*25+i+1}))});
const catalogo = (count=1,page=1,extra={}) => ({count,results:Array.from({length:Math.max(0,Math.min(25,count-(page-1)*25))},(_,i)=>producto({id:(page-1)*25+i+1,...extra}))});
async function pantalla(t,config={}) {
    const dom = new JSDOM(html,{url:'http://localhost/transferencias/',runScripts:'outside-only',pretendToBeVisual:true});
    t.after(()=>dom.window.close()); const w=dom.window,requests=[],timers=new Map(),modales=new Map();let timer=0,avisos=0,lectura;
    w.localStorage.setItem('access_token','test');w.localStorage.setItem('refresh_token','refresh');
    w.localStorage.setItem('usuario',JSON.stringify({id:config.usuario||7,nombre_completo:'Persona Prueba',rol_nombre:'Encargado de bodega'}));
    if(config.pendiente)w.sessionStorage.setItem('ss-transferencia-pendiente:'+(config.propietario||7),config.pendiente);
    w.HTMLElement.prototype.scrollIntoView=()=>{};w.matchMedia=()=>({matches:true});w.smartstockClearSession=()=>w.localStorage.clear();
    w.bootstrap={Modal:{getOrCreateInstance(elemento){
        if(!modales.has(elemento))modales.set(elemento,{
            show(){elemento.dispatchEvent(new w.Event('show.bs.modal'));elemento.classList.add('show');elemento.dispatchEvent(new w.Event('shown.bs.modal'));},
            hide(){if(!elemento.dispatchEvent(new w.Event('hide.bs.modal',{cancelable:true})))return;elemento.classList.remove('show');elemento.dispatchEvent(new w.Event('hidden.bs.modal'));},
        });return modales.get(elemento);
    }}};
    w.Html5QrcodeSupportedFormats={};w.Html5Qrcode=class{async start(_c,_o,fn){lectura=fn;}async stop(){}clear(){}};
    w.setTimeout=fn=>{timers.set(++timer,fn);return timer;};w.clearTimeout=id=>timers.delete(id);
    w.fetch=(url,options)=>new Promise((resolve,reject)=>requests.push({url:new URL(url,w.location.href),options,resolve,reject}));
    w.addEventListener('smartstock:notifications-changed',()=>avisos++);
    w.eval(fuente);if(config.camara)w.eval(camara);await tick();const el=id=>w.document.getElementById(id);
    const responder=async(i,data,status=200)=>{assert.ok(requests[i],`Falta solicitud ${i}`);requests[i].resolve({ok:status>=200&&status<300,status,json:async()=>data});await tick();};
    const campo=(id,value,event='input')=>{el(id).value=value;el(id).dispatchEvent(new w.Event(event));};
    const enviar=()=>el('formTransferencia').dispatchEvent(new w.Event('submit',{cancelable:true}));
    const cargar=async(d=opciones(),historial=lista())=>{await responder(0,historial);await responder(1,d);};
    const debounce=async()=>{const callbacks=[...timers.values()];timers.clear();callbacks.forEach(fn=>fn());await tick();};
    const abrir=async(d=catalogo())=>{el('nuevaTransferencia').click();assert.equal(el('transferenciaDestino').value,'');campo('transferenciaDestino','2','change');await responder(requests.length-1,d);if([...el('transferenciaProducto').options].some(o=>o.value==='1'))campo('transferenciaProducto','1','change');};
    const ocultar=id=>modales.get(el(id)).hide();
    return {w,el,requests,responder,campo,enviar,cargar,abrir,debounce,ocultar,lectura:()=>lectura,avisos:()=>avisos};
}

test('el historial filtra por ambas bodegas, estado y fechas y conserva filtros al paginar',async t=>{
    const c=await pantalla(t);await c.cargar(opciones(),lista(32));
    c.campo('buscarTransferencias','Taladro');await c.debounce();await c.responder(2,lista(32));
    for(const [id,valor]of[['origenTransferencias','1'],['destinoTransferencias','4'],['estadoTransferencias','COMPLETADA'],['desdeTransferencias','2026-10-01'],['hastaTransferencias','2026-11-01']]){c.campo(id,valor,'change');await c.responder(c.requests.length-1,lista(32));}
    c.el('paginacionTransferencias').querySelector('[data-page="2"]').click();const p=c.requests.at(-1).url.searchParams;
    assert.deepEqual(Object.fromEntries(p),{page:'2',search:'Taladro',origen:'1',destino:'4',estado:'COMPLETADA',desde:'2026-10-01',hasta:'2026-11-01'});
    await c.responder(c.requests.length-1,lista(32,2));assert.match(c.el('resumenTransferencias').textContent,/26–32 de 32/);
    assert.match(c.el('mostrarFiltrosTransferencias').textContent,/\(5\)/);assert.match(c.el('destinoTransferencias').textContent,/Antigua.*inactiva/);
    c.el('limpiarTransferencias').click();assert.equal(c.requests.at(-1).url.search,'?page=1');
});

test('búsquedas viejas no reemplazan los resultados y el rango de fechas inválido no consulta',async t=>{
    const c=await pantalla(t);await c.responder(1,opciones());c.campo('buscarTransferencias','Nuevo');await c.responder(0,lista());
    assert.equal(c.el('listaTransferencias').querySelector('button'),null);await c.debounce();await c.responder(2,lista(0));
    c.campo('desdeTransferencias','2026-11-03','change');await c.responder(3,lista(0));c.campo('hastaTransferencias','2026-11-01','change');
    assert.equal(c.requests.length,4);assert.match(c.el('errorHistorialTransferencias').textContent,/fecha inicial/);assert.equal(c.el('listaTransferencias').getAttribute('aria-busy'),'false');
});

test('una página desaparecida se recupera con last una sola vez',async t=>{
    const c=await pantalla(t);await c.cargar(opciones(),lista(32));c.el('paginacionTransferencias').querySelector('[data-page="2"]').click();
    await c.responder(2,{detail:'No existe'},404);assert.equal(c.requests[3].url.searchParams.get('page'),'last');await c.responder(3,lista(1));
    assert.match(c.el('resumenTransferencias').textContent,/1–1 de 1/);assert.equal(c.el('paginacionTransferencias').children.length,0);
});

test('errores del historial y de bodegas se pueden reintentar por separado',async t=>{
    const c=await pantalla(t);await c.responder(0,{mensaje:'Historial temporalmente no disponible'},503);await c.responder(1,{mensaje:'Bodegas temporalmente no disponibles'},503);
    assert.equal(c.el('nuevaTransferencia').disabled,true);assert.equal(c.el('reintentarHistorialTransferencias').hidden,false);
    c.el('actualizarBodegasTransferencias').click();await c.responder(2,opciones());c.el('reintentarHistorialTransferencias').click();await c.responder(3,lista());
    assert.equal(c.el('nuevaTransferencia').disabled,false);assert.equal(c.el('errorHistorialTransferencias').hidden,true);
});

test('un lector consulta el historial y no puede abrir un registro nuevo',async t=>{
    const c=await pantalla(t);await c.cargar(opciones({permisos:{registrar:false}}));c.el('nuevaTransferencia').click();c.enviar();
    assert.equal(c.el('nuevaTransferencia').disabled,true);assert.equal(c.requests.length,2);assert.match(c.el('estadoBodegasTransferencias').textContent,/consulta/);
    assert.equal(c.el('menu-auditoria').hidden,true);c.el('listaTransferencias').querySelector('button').click();assert.equal(c.requests[2].options.method,undefined);
});

test('se necesitan dos bodegas activas y las opciones de origen y destino son independientes',async t=>{
    const c=await pantalla(t);await c.cargar(opciones({bodegas:[{id:1,nombre:'Central'}]}));assert.equal(c.el('nuevaTransferencia').disabled,true);
    c.el('actualizarBodegasTransferencias').click();await c.responder(2,opciones());c.el('nuevaTransferencia').click();
    assert.equal(c.el('transferenciaOrigen').value,'1');assert.equal(c.el('transferenciaDestino').value,'');assert.equal(c.el('confirmarTransferencia').disabled,true);
    c.campo('transferenciaDestino','1','change');c.enviar();assert.equal(c.requests.length,3);assert.match(c.el('resumenNuevaTransferencia').textContent,/distintas/);
});

test('detalle muestra existencias históricas y admite registros antiguos con varios productos',async t=>{
    const c=await pantalla(t);await c.cargar();c.el('listaTransferencias').querySelector('button').click();await c.responder(2,{data:transferencia()});
    assert.match(c.el('detalleTransferenciaStock').textContent,/24 → 18.*6 → 12/);assert.match(c.el('detalleTransferenciaMovimientos').textContent,/salida #1 y entrada #2/);
    c.ocultar('modalDetalleTransferencia');c.el('listaTransferencias').querySelector('button').click();
    await c.responder(3,{data:transferencia({estado:'PENDIENTE',stock:null,movimientos:null,detalles:[{sku:'A',producto:'Producto A',cantidad:4},{sku:'B',producto:'Producto B',cantidad:7}]})});
    assert.equal(c.el('detalleTransferenciaProductos').children.length,2);assert.equal(c.el('detalleTransferenciaEstado').textContent,'Pendiente');assert.match(c.el('detalleTransferenciaStock').textContent,/no tiene una instantánea/);
});

test('cerrar un detalle descarta su respuesta tardía y devuelve el foco',async t=>{
    const c=await pantalla(t);await c.cargar();const b=c.el('listaTransferencias').querySelector('button');b.click();c.ocultar('modalDetalleTransferencia');await c.responder(2,{data:transferencia()});
    assert.equal(c.el('datosDetalleTransferencia').hidden,true);assert.equal(c.w.document.activeElement,b);
});

test('nombres, SKU y responsables se muestran como texto en filas y detalles',async t=>{
    const c=await pantalla(t),malicioso='<img src=x onerror=alert(1)>',d=transferencia({usuario:malicioso,detalles:[{sku:malicioso,producto:malicioso,cantidad:1}]});
    await c.cargar(opciones(),{count:1,results:[d]});c.el('listaTransferencias').querySelector('button').click();await c.responder(2,{data:d});
    assert.equal(c.el('listaTransferencias').querySelector('img'),null);assert.equal(c.el('datosDetalleTransferencia').querySelector('img'),null);assert.match(c.el('listaTransferencias').textContent,/<img/);
});

test('el formulario consulta cantidades de las bodegas elegidas y previsualiza ambos stocks',async t=>{
    const c=await pantalla(t);await c.cargar();await c.abrir();assert.equal(c.requests[2].url.searchParams.get('origen'),'1');assert.equal(c.requests[2].url.searchParams.get('destino'),'2');
    c.campo('transferenciaCantidad','6');assert.match(c.el('stockOrigenTransferencia').textContent,/24.*18/);assert.match(c.el('stockDestinoTransferencia').textContent,/6.*12/);assert.equal(c.el('confirmarTransferencia').disabled,false);
    assert.match(c.el('resumenNuevaTransferencia').textContent,/6 unidades.*Central.*Norte/);
});

test('cantidades inválidas y stock insuficiente bloquean el envío',async t=>{
    const c=await pantalla(t);await c.cargar();await c.abrir();
    for(const cantidad of ['0','-1','1.5','25','2147483648','']){c.campo('transferenciaCantidad',cantidad);c.enviar();assert.equal(c.el('confirmarTransferencia').disabled,true);assert.equal(c.requests.length,3);}
    c.campo('transferenciaCantidad','24');assert.equal(c.el('confirmarTransferencia').disabled,false);
});

test('un destino negativo o que desborda el límite bloquea el traslado',async t=>{
    for(const stock_destino of [-1,2147483647]){const c=await pantalla(t);await c.cargar();await c.abrir(catalogo(1,1,{stock_destino}));c.enviar();assert.equal(c.el('confirmarTransferencia').disabled,true);assert.equal(c.requests.length,3);}
});

test('cambiar de bodegas limpia la selección y descarta resultados del contexto anterior',async t=>{
    const c=await pantalla(t);await c.cargar();c.el('nuevaTransferencia').click();c.campo('transferenciaDestino','2','change');c.campo('transferenciaDestino','3','change');
    await c.responder(2,catalogo());assert.equal(c.el('transferenciaProducto').options.length,1);await c.responder(3,catalogo(1,1,{bodega_destino_id:3}));
    c.campo('transferenciaProducto','1','change');assert.equal(c.el('confirmarTransferencia').disabled,false);c.campo('transferenciaOrigen','3','change');assert.equal(c.el('previsionTransferencia').hidden,true);assert.equal(c.el('confirmarTransferencia').disabled,true);
});

test('la interfaz rechaza un catálogo que corresponda a otras bodegas',async t=>{
    const c=await pantalla(t);await c.cargar();await c.abrir(catalogo(1,1,{bodega_destino_id:3}));assert.equal(c.el('confirmarTransferencia').disabled,true);assert.match(c.el('errorNuevaTransferencia').textContent,/estas bodegas/);
    c.el('reintentarProductosTransferencia').click();await c.responder(3,catalogo());assert.equal(c.el('transferenciaProducto').options.length,2);
});

test('catálogo paginado y búsqueda no permiten conservar un producto fuera de la consulta',async t=>{
    const c=await pantalla(t);await c.cargar();await c.abrir(catalogo(28));c.el('productosTransferenciaSiguiente').click();assert.equal(c.requests[3].url.searchParams.get('page'),'2');assert.equal(c.el('confirmarTransferencia').disabled,true);
    await c.responder(3,catalogo(28,2));assert.match(c.el('resumenProductosTransferencia').textContent,/26–28 de 28/);c.campo('transferenciaProducto','26','change');
    c.campo('transferenciaBuscarProducto','Sin resultados');assert.equal(c.el('confirmarTransferencia').disabled,true);await c.debounce();assert.equal(c.requests[4].url.searchParams.get('search'),'Sin resultados');assert.equal(c.requests[4].url.searchParams.get('page'),'1');
    await c.responder(4,catalogo(0));assert.match(c.el('resumenProductosTransferencia').textContent,/0 productos/);
});

test('resolver SKU o código registrado selecciona un producto que no está en la página',async t=>{
    const c=await pantalla(t);await c.cargar();await c.abrir(catalogo(50));c.campo('transferenciaCodigo','QR-registrado');c.el('transferenciaCodigo').dispatchEvent(new c.w.KeyboardEvent('keydown',{key:'Enter',cancelable:true}));
    assert.equal(c.requests[3].url.searchParams.get('codigo'),'QR-registrado');await c.responder(3,{data:producto({id:99,sku:'QR-99'})});
    assert.equal(c.el('transferenciaProducto').value,'99');c.enviar();assert.equal(JSON.parse(c.requests[4].options.body).producto_id,99);
});

test('código sin existencias explica el rechazo y una búsqueda fallida no deja paginación vieja',async t=>{
    const c=await pantalla(t);await c.cargar();await c.abrir(catalogo(50));c.campo('transferenciaCodigo','CERO');c.el('buscarCodigoTransferencia').click();await c.responder(3,{data:producto({stock_origen:0})});
    assert.match(c.el('resumenNuevaTransferencia').textContent,/hay 0 unidades/);assert.equal(c.el('confirmarTransferencia').disabled,true);
    c.campo('transferenciaCodigo','DESCONOCIDO');c.el('buscarCodigoTransferencia').click();await c.responder(4,{mensaje:'Código no registrado'},404);
    assert.equal(c.el('productosTransferenciaSiguiente').disabled,true);assert.equal(c.el('transferenciaProducto').options.length,1);assert.match(c.el('errorNuevaTransferencia').textContent,/no registrado/);
});

test('confirmar evita doble envío, cierra solo al terminar y actualiza una vez la campana',async t=>{
    const c=await pantalla(t);await c.cargar();await c.abrir();c.campo('transferenciaCantidad','6');c.enviar();c.enviar();c.ocultar('modalTransferencia');
    assert.equal(c.requests.length,4);assert.equal(c.el('modalTransferencia').classList.contains('show'),true);const p=JSON.parse(c.requests[3].options.body);
    assert.deepEqual({...p,solicitud_id:'UUID'},{bodega_origen_id:1,bodega_destino_id:2,producto_id:1,cantidad:6,solicitud_id:'UUID'});assert.match(p.solicitud_id,/^[0-9a-f-]{36}$/);
    assert.ok(c.w.sessionStorage.getItem('ss-transferencia-pendiente:7'));await c.responder(3,{success:true,data:transferencia()},201);
    assert.equal(c.el('modalTransferencia').classList.contains('show'),false);assert.equal(c.avisos(),1);assert.equal(c.w.sessionStorage.getItem('ss-transferencia-pendiente:7'),null);c.enviar();assert.equal(c.requests.length,5);
});

test('un conflicto de stock conserva datos, actualiza disponibles y permite corregir la cantidad',async t=>{
    const c=await pantalla(t);await c.cargar();await c.abrir();c.campo('transferenciaCantidad','6');c.enviar();await c.responder(3,{mensaje:'Stock insuficiente',errores:{stock_origen:3,stock_destino:8}},409);
    assert.equal(c.el('transferenciaCantidad').value,'6');assert.match(c.el('stockOrigenTransferencia').textContent,/3/);assert.equal(c.el('confirmarTransferencia').disabled,true);assert.equal(c.el('transferenciaOrigen').disabled,false);assert.equal(c.avisos(),0);
    c.campo('transferenciaCantidad','2');c.enviar();assert.equal(JSON.parse(c.requests[4].options.body).cantidad,2);assert.equal(JSON.parse(c.requests[4].options.body).solicitud_id,JSON.parse(c.requests[3].options.body).solicitud_id);
});

test('una conexión perdida congela datos y reintenta la misma confirmación sin crear otra',async t=>{
    const c=await pantalla(t);await c.cargar();await c.abrir();c.enviar();const cuerpo=c.requests[3].options.body;c.requests[3].reject(new TypeError('Sin conexión'));await tick();
    assert.equal(c.el('transferenciaCantidad').disabled,true);assert.equal(c.el('transferenciaDestino').disabled,true);assert.equal(c.el('confirmarTransferencia').disabled,false);assert.match(c.el('confirmarTransferencia').textContent,/Verificar/);
    c.campo('transferenciaCantidad','20');c.enviar();assert.equal(c.requests[4].options.body,cuerpo);await c.responder(4,{success:true,data:transferencia()},200);assert.equal(c.avisos(),1);
});

test('errores 500 y confirmaciones ilegibles conservan la clave para recuperar el resultado',async t=>{
    for(const caso of ['500','json','null','sin datos']){const c=await pantalla(t);await c.cargar();await c.abrir();c.enviar();const body=c.requests[3].options.body;
        if(caso==='500')await c.responder(3,{mensaje:'Fallo temporal'},503);
        else if(caso==='json'){c.requests[3].resolve({ok:true,status:201,json:async()=>{throw new SyntaxError('Cortado');}});await tick();}
        else if(caso==='null')await c.responder(3,null,201);
        else await c.responder(3,{success:true},201);
        assert.equal(c.el('confirmarTransferencia').disabled,false);assert.equal(c.el('transferenciaCantidad').disabled,true);c.enviar();assert.equal(c.requests[4].options.body,body);
    }
});

test('una solicitud utilizada con otros datos bloquea la confirmación y pide revisar historial',async t=>{
    const c=await pantalla(t);await c.cargar();await c.abrir();c.enviar();await c.responder(3,{mensaje:'Revisa el historial',errores:{codigo:'SOLICITUD_UTILIZADA',transferencia_id:20}},409);
    assert.equal(c.el('confirmarTransferencia').disabled,true);assert.equal(c.w.sessionStorage.getItem('ss-transferencia-pendiente:7'),null);assert.match(c.el('errorNuevaTransferencia').textContent,/historial/);
});

test('cerrar y volver a abrir una confirmación incierta recupera el mismo cuerpo',async t=>{
    const c=await pantalla(t);await c.cargar();await c.abrir();c.enviar();c.requests[3].reject(new Error('Sin conexión'));await tick();const body=c.requests[3].options.body;
    c.ocultar('modalTransferencia');assert.equal(c.el('avisoTransferenciaPendiente').hidden,false);c.el('reanudarTransferencia').click();c.enviar();assert.equal(c.requests.at(-1).options.body,body);assert.match(c.el('tituloNuevaTransferencia').textContent,/Verificar/);
});

test('recargar la pestaña conserva una solicitud incierta vinculada al usuario',async t=>{
    const a=await pantalla(t);await a.cargar();await a.abrir();a.enviar();const guardada=a.w.sessionStorage.getItem('ss-transferencia-pendiente:7');
    const b=await pantalla(t,{pendiente:guardada});await b.cargar(opciones({bodegas:[{id:3,nombre:'Sur'}]}));b.el('reanudarTransferencia').click();b.enviar();
    assert.equal(b.requests[2].options.body,a.requests[3].options.body);assert.equal(b.el('transferenciaCantidad').disabled,true);
    const otro=await pantalla(t,{pendiente:guardada,usuario:8});await otro.cargar();assert.equal(otro.el('avisoTransferenciaPendiente').hidden,true);
});

test('datos incompletos o manipulados del almacenamiento no se reenvían',async t=>{
    for(const pendiente of ['{invalido',JSON.stringify({payload:{producto_id:1},producto:producto()})]){const c=await pantalla(t,{pendiente});await c.cargar();assert.equal(c.el('avisoTransferenciaPendiente').hidden,true);assert.equal(c.requests.length,2);}
});

test('JWT vencido renueva una sola vez dos consultas simultáneas',async t=>{
    const c=await pantalla(t);await c.responder(0,{detail:'Expirado'},401);await c.responder(1,{detail:'Expirado'},401);assert.equal(c.requests.length,3);assert.equal(c.requests[2].url.pathname,'/api/v1/auth/refresh/');
    await c.responder(2,{access:'nuevo'});assert.equal(c.requests.length,5);assert.equal(c.requests[3].options.headers.Authorization,'Bearer nuevo');assert.equal(c.requests[4].options.headers.Authorization,'Bearer nuevo');
    await c.responder(3,lista());await c.responder(4,opciones());assert.equal(c.el('nuevaTransferencia').disabled,false);
});

test('renovar JWT durante el POST mantiene la clave y todo el cuerpo del traslado',async t=>{
    const c=await pantalla(t);await c.cargar();await c.abrir();c.enviar();const body=c.requests[3].options.body;await c.responder(3,{detail:'Expirado'},401);await c.responder(4,{access:'rotado',refresh:'refresh-rotado'});
    assert.equal(c.requests[5].options.body,body);assert.equal(c.requests[5].options.headers.Authorization,'Bearer rotado');assert.equal(c.w.localStorage.getItem('refresh_token'),'refresh-rotado');await c.responder(5,{data:transferencia()},201);assert.equal(c.avisos(),1);
});

test('la cámara usa dos lecturas, vuelve al formulario y resuelve sin perder bodegas ni cantidad',async t=>{
    const c=await pantalla(t,{camara:true});await c.cargar();await c.abrir();c.campo('transferenciaCantidad','6');c.el('camaraTransferencia').click();await tick();
    assert.equal(c.el('modalTransferencia').classList.contains('show'),false);assert.equal(c.el('ssModalCamara').classList.contains('show'),true);c.lectura()('CODIGO-99');assert.equal(c.requests.length,3);c.lectura()('CODIGO-99');await tick();
    assert.equal(c.el('modalTransferencia').classList.contains('show'),true);assert.equal(c.el('transferenciaCantidad').value,'6');assert.equal(c.el('transferenciaDestino').value,'2');assert.equal(c.requests[3].url.searchParams.get('codigo'),'CODIGO-99');
    await c.responder(3,{data:producto({id:99})});c.enviar();assert.equal(JSON.parse(c.requests[4].options.body).producto_id,99);
});

test('cancelar la cámara conserva el producto y la cantidad ya preparados',async t=>{
    const c=await pantalla(t,{camara:true});await c.cargar();await c.abrir();c.campo('transferenciaCantidad','6');c.el('camaraTransferencia').click();await tick();c.ocultar('ssModalCamara');
    assert.equal(c.el('modalTransferencia').classList.contains('show'),true);assert.equal(c.el('transferenciaProducto').value,'1');assert.equal(c.el('transferenciaCantidad').value,'6');assert.equal(c.el('confirmarTransferencia').disabled,false);assert.equal(c.requests.length,3);
});

test('cerrar un formulario descarta consultas de productos todavía en curso',async t=>{
    const c=await pantalla(t);await c.cargar();c.el('nuevaTransferencia').click();c.campo('transferenciaDestino','2','change');c.ocultar('modalTransferencia');await c.responder(2,catalogo());
    assert.equal(c.el('transferenciaProducto').options.length,1);assert.equal(c.el('confirmarTransferencia').disabled,true);
});

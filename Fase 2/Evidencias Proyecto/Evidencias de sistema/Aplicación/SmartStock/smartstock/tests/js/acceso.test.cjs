const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');
const root=path.resolve(__dirname,'../..');
const fuente=n=>readFileSync(path.join(root,n),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function pantalla(t,tipo='login'){
 const plantilla=tipo==='login'?'templates/login.html':tipo==='recuperar'?'templates/usuarios/recuperar_clave.html':'templates/usuarios/nueva_clave.html';
 const dom=new JSDOM(fuente(plantilla).replace(/{%[\s\S]*?%}/g,'').replace(/{{[\s\S]*?}}/g,''),{url:'http://localhost/',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:new VirtualConsole()});
 const w=dom.window,requests=[];t.after(()=>w.close());
 if(tipo==='login'){
  const login=w.document.getElementById('login-form');
  login.action='/api/v1/auth/login-web/';
  const csrf=w.document.createElement('input');
  Object.assign(csrf,{type:'hidden',name:'csrfmiddlewaretoken',value:'csrf-prueba'});
  login.appendChild(csrf);
 }
 w.fetch=(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));
 w.eval(fuente('static/js/password_visibility.js'));w.eval(fuente('static/js/acceso.js'));w.eval(fuente('static/js/login.js'));await tick();
 const el=id=>w.document.getElementById(id),form=w.document.querySelector('form');
 const enviar=()=>{const e=new w.Event('submit',{cancelable:true});form.dispatchEvent(e);return e;};
 const campo=(id,value)=>{el(id).value=value;el(id).dispatchEvent(new w.Event('input'));};
 const responder=async(data,status=200)=>{requests.at(-1).resolve({ok:status>=200&&status<300,status,json:async()=>data});await tick();};
 const completar=()=>{if(tipo==='login'){campo('email','persona@example.com');campo('password',' Clave con espacios 123! ');}else if(tipo==='recuperar')campo('id_email','persona@example.com');else{campo('id_new_password1','NuevaClaveSegura123!');campo('id_new_password2','NuevaClaveSegura123!');}};
 return{w,el,form,requests,enviar,campo,responder,completar};
}
const exito=()=>({success:true,data:{access:'access-prueba',refresh:'refresh-prueba',usuario:{id:7,nombre_completo:'Persona Prueba'}}});

test('login inválido no envía solicitudes y un envío válido preserva espacios de la contraseña',async t=>{
 const c=await pantalla(t);c.enviar();assert.equal(c.requests.length,0);c.completar();c.enviar();
 assert.deepEqual(JSON.parse(c.requests[0].options.body),{email:'persona@example.com',password:' Clave con espacios 123! '});assert.equal(c.requests[0].options.cache,'no-store');
 assert.equal(c.requests[0].url,'http://localhost/api/v1/auth/login-web/');assert.equal(c.requests[0].options.headers['X-CSRFToken'],'csrf-prueba');
});
test('login pendiente bloquea envíos repetidos y muestra el estado de procesamiento',async t=>{
 const c=await pantalla(t);c.completar();c.enviar();c.enviar();assert.equal(c.requests.length,1);assert.equal(c.el('login-submit').disabled,true);assert.equal(c.form.getAttribute('aria-busy'),'true');assert.match(c.el('login-submit').textContent,/Iniciando sesión/);assert.equal(c.el('password').readOnly,true);
 await c.responder({mensaje:'No existe esa cuenta'},401);assert.equal(c.el('login-submit').disabled,false);assert.equal(c.el('password').readOnly,false);assert.equal(c.el('password').value,' Clave con espacios 123! ');assert.equal(c.w.document.activeElement,c.el('alert-box'));assert.doesNotMatch(c.el('alert-box').textContent,/No existe/);
 c.enviar();assert.equal(c.requests.length,2);
});
test('error de red permite corregir los datos y reintentar sin perder preferencias',async t=>{
 const c=await pantalla(t);c.w.localStorage.setItem('smartstock-theme','dark');c.completar();c.enviar();c.requests[0].reject(new c.w.TypeError('Failed to fetch'));await tick();assert.match(c.el('alert-box').textContent,/Revisa tu conexión/);assert.equal(c.form.getAttribute('aria-busy'),'false');
 c.campo('password','Otra clave');assert.equal(c.el('alert-box').hidden,true);c.enviar();assert.equal(JSON.parse(c.requests[1].options.body).password,'Otra clave');assert.equal(c.w.localStorage.getItem('smartstock-theme'),'dark');
});
test('errores del servidor se muestran como texto y no se ejecuta HTML',async t=>{
 const c=await pantalla(t);c.completar();c.enviar();await c.responder({mensaje:'<img src=x onerror=alert(1)>'},400);assert.equal(c.el('alert-box').querySelector('img'),null);assert.match(c.el('alert-box').textContent,/<img/);
});
test('respuestas incompletas o ilegibles no guardan tokens ni dejan bloqueado el formulario',async t=>{
 for(const caso of ['json','sin usuario','sin refresh']){
  const c=await pantalla(t);c.completar();c.enviar();
  if(caso==='json'){c.requests[0].resolve({ok:true,status:200,json:async()=>{throw new SyntaxError('Inválido');}});await tick();}
  else{const d=exito();delete d.data[caso==='sin usuario'?'usuario':'refresh'];await c.responder(d);}
  assert.equal(c.w.localStorage.getItem('access_token'),null);assert.equal(c.el('login-submit').disabled,false);assert.equal(c.el('alert-box').hidden,false);
 }
});
test('errores 429 y 503 explican cómo reintentar sin mostrar detalles internos',async t=>{
 for(const [status,texto]of[[429,/Espera un momento/],[503,/en este momento/]]){const c=await pantalla(t);c.completar();c.enviar();await c.responder({mensaje:'Traceback privado'},status);assert.match(c.el('alert-box').textContent,texto);assert.doesNotMatch(c.el('alert-box').textContent,/Traceback/);assert.equal(c.el('login-submit').disabled,false);}
});
test('inicio exitoso guarda la sesión y conserva el bloqueo mientras navega',async t=>{
 const c=await pantalla(t);c.completar();c.enviar();await c.responder(exito());assert.equal(c.w.localStorage.getItem('access_token'),'access-prueba');assert.equal(JSON.parse(c.w.localStorage.getItem('usuario')).id,7);assert.equal(c.w.localStorage.getItem('password'),null);assert.match(c.el('login-submit').textContent,/Abriendo SmartStock/);assert.equal(c.el('login-submit').disabled,true);c.enviar();assert.equal(c.requests.length,1);
});
test('fallar al guardar la sesión limpia tokens parciales y conserva el tema',async t=>{
 const c=await pantalla(t);c.w.localStorage.setItem('smartstock-theme','dark');const original=c.w.Storage.prototype.setItem;
 c.w.Storage.prototype.setItem=function(k,v){if(k==='refresh_token')throw new c.w.DOMException('Cuota','QuotaExceededError');return original.call(this,k,v);};
 c.completar();c.enviar();await c.responder(exito());assert.equal(c.w.localStorage.getItem('access_token'),null);assert.equal(c.w.localStorage.getItem('usuario'),null);assert.equal(c.w.localStorage.getItem('smartstock-theme'),'dark');assert.match(c.el('alert-box').textContent,/almacenamiento/);assert.equal(c.el('login-submit').disabled,false);
});
test('mostrar u ocultar contraseña conserva su valor y actualiza la etiqueta accesible',async t=>{
 const c=await pantalla(t);c.completar();const b=c.w.document.querySelector('[data-password-toggle]');b.click();assert.equal(c.el('password').type,'text');assert.equal(b.getAttribute('aria-label'),'Ocultar contraseña');assert.equal(b.getAttribute('aria-pressed'),'true');b.click();assert.equal(c.el('password').type,'password');assert.equal(c.el('password').value,' Clave con espacios 123! ');assert.equal(b.getAttribute('aria-label'),'Mostrar contraseña');
});
test('recuperación usa POST nativo, mantiene el correo y bloquea un segundo envío',async t=>{
 const c=await pantalla(t,'recuperar');c.completar();assert.equal(c.enviar().defaultPrevented,false);assert.equal(c.enviar().defaultPrevented,true);const boton=c.form.querySelector('[type=submit]');assert.match(boton.textContent,/Enviando enlace/);assert.equal(boton.disabled,true);assert.equal(c.el('id_email').disabled,false);assert.equal(new c.w.FormData(c.form).get('email'),'persona@example.com');assert.equal(c.requests.length,0);
});
test('recuperación con correo inválido conserva el botón disponible',async t=>{
 const c=await pantalla(t,'recuperar');c.campo('id_email','inválido');assert.equal(c.enviar().defaultPrevented,true);assert.equal(c.form.querySelector('[type=submit]').disabled,false);assert.equal(c.form.getAttribute('aria-busy'),'false');
});
test('nueva contraseña conserva ambos campos en FormData durante el envío',async t=>{
 const c=await pantalla(t,'nueva');c.completar();c.enviar();const data=new c.w.FormData(c.form);assert.equal(data.get('new_password1'),'NuevaClaveSegura123!');assert.equal(data.get('new_password2'),'NuevaClaveSegura123!');assert.equal(c.form.getAttribute('aria-busy'),'true');assert.match(c.form.querySelector('[type=submit]').textContent,/Guardando contraseña/);
});
test('volver por historial restaura los formularios que quedaron en estado de envío',async t=>{
 for(const tipo of ['login','recuperar','nueva']){const c=await pantalla(t,tipo);c.completar();c.enviar();c.w.dispatchEvent(new c.w.PageTransitionEvent('pageshow',{persisted:true}));assert.equal(c.form.getAttribute('aria-busy'),'false');assert.equal(c.form.querySelector('[type=submit]').disabled,false);assert.equal(c.form.querySelector('input:not([type=hidden])').readOnly,false);}
});

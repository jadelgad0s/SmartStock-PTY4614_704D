const activas = [
    {id: 1, nombre: 'Bodega Central', etiqueta: 'Bodega Central', activa: true},
    {id: 2, nombre: 'Bodega Norte', etiqueta: 'Bodega Norte', activa: true},
];
module.exports = () => ({data: {
    bodegas: activas, bodegas_historial: [...activas, {id: 3, nombre: 'Antigua', activa: false}],
    bodega_predeterminada: 1,
    permisos: {crear: true, editar: true, desactivar: true, auditoria: true, usuarios: true, configuracion: true},
    operar: {entrada: true, salida: true, merma: true},
}});

"""
Serializers del módulo de productos.
"""
from rest_framework import serializers
from django.db import transaction
from django.core.validators import RegexValidator
from .models import Producto, CodigoBarra, FichaProductoExterna
from .consulta_codigos import interpretar_codigo, procedencia, productos_registrados
from .stock import estado_stock, existencias_producto


class CodigoBarraSerializer(serializers.ModelSerializer):
    """Serializer de códigos de barras, validado por el producto padre."""
    # Evita el UniqueValidator anidado: permite conservar códigos ya
    # asignados al MISMO producto durante una actualización.
    codigo = serializers.CharField(max_length=100)

    class Meta:
        model = CodigoBarra
        fields = ('id', 'codigo', 'tipo', 'es_principal', 'fecha_creacion')
        read_only_fields = ('id', 'fecha_creacion')

    def validate_codigo(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('El código no puede estar vacío.')
        return value


class ProductoListSerializer(serializers.ModelSerializer):
    """Serializer para listar productos con su stock en tiempo real."""
    codigo_principal = serializers.SerializerMethodField()
    stock_actual = serializers.SerializerMethodField()
    stock_minimo = serializers.SerializerMethodField()
    estado_stock = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = (
            'id', 'sku', 'nombre', 'precio_referencia',
            'codigo_principal', 'activo', 'fecha_creacion', 'stock_actual', 'stock_minimo', 'estado_stock'
        )
        read_only_fields = ('id', 'fecha_creacion')

    def get_stock_actual(self, obj):
        if hasattr(obj, 'stock_calculado'):
            return obj.stock_calculado
        from django.db.models import Sum
        # Sumamos todo el stock físico que haya en las bodegas para este producto
        total = obj.stockbodega_set.aggregate(total=Sum('cantidad_total'))['total']
        return total or 0

    def get_codigo_principal(self, obj):
        return next((c.codigo for c in obj.codigos_barra.all() if c.es_principal), None)

    def get_stock_minimo(self, obj):
        return max(0, obj.minimo_calculado) if self.context.get('bodega_id') is not None else None

    def get_estado_stock(self, obj):
        return estado_stock(obj.stock_calculado, obj.minimo_calculado) if self.context.get('bodega_id') is not None else None


class ProductoDetailSerializer(serializers.ModelSerializer):
    """Serializer detallado de un producto."""
    codigos_barra = CodigoBarraSerializer(many=True, read_only=True)
    existencias = serializers.SerializerMethodField()
    fuente_externa = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = (
            'id', 'sku', 'nombre', 'descripcion', 'precio_referencia',
            'imagen', 'codigos_barra', 'activo',
            'fecha_creacion', 'fecha_modificacion', 'existencias', 'fuente_externa'
        )
        read_only_fields = ('id', 'fecha_creacion', 'fecha_modificacion')

    def get_existencias(self, obj):
        return existencias_producto(obj.pk)

    def get_fuente_externa(self, obj):
        return procedencia(obj.ficha_externa) if obj.ficha_externa_id else None


class SKUField(serializers.CharField):
    """Normalizar antes de aplicar el patrón, incluidos SKU escritos en minúsculas."""
    def to_internal_value(self, data):
        return super().to_internal_value(data).strip().upper()


class ProductoCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer para crear/actualizar productos con sus códigos."""
    codigos_barra = CodigoBarraSerializer(many=True, required=False)
    ficha_externa_id = serializers.PrimaryKeyRelatedField(
        source='ficha_externa', queryset=FichaProductoExterna.objects.exclude(datos={}),
        required=False, allow_null=True, write_only=True,
    )
    sku = SKUField(max_length=50, validators=[RegexValidator(regex=r'^[A-Z0-9\-_]+$', message='Usa letras, números, guion o guion bajo para el SKU.')])

    class Meta:
        model = Producto
        fields = (
            'sku', 'nombre', 'descripcion', 'precio_referencia',
            'imagen', 'codigos_barra', 'ficha_externa_id'
        )

    def validate_codigos_barra(self, value):
        codigos = [c['codigo'] for c in value]
        if len(codigos) != len(set(codigos)):
            raise serializers.ValidationError('Hay códigos de barras repetidos.')
        principales = sum(bool(c.get('es_principal')) for c in value)
        if principales > 1:
            raise serializers.ValidationError('Solo puede haber un código principal.')
        conflictos = CodigoBarra.objects.filter(codigo__in=codigos)
        if self.instance:
            conflictos = conflictos.exclude(producto_id=self.instance.id)
        if conflictos.exists():
            raise serializers.ValidationError('Uno de los códigos pertenece a otro producto.')
        return value

    def validate_sku(self, value):
        """SKU debe ser único incluso entre productos inactivos."""
        value = value.upper().strip()
        qs = Producto.objects.filter(sku__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                'Ya existe un producto con este SKU.'
            )
        return value

    def validate(self, attrs):
        ficha = attrs.get('ficha_externa')
        if ficha:
            codigos = attrs.get('codigos_barra')
            if codigos is None:
                codigos = list(self.instance.codigos_barra.values('codigo')) if self.instance else []
            gtins = [interpretar_codigo(c['codigo'])[0] for c in codigos]
            if not any(g and g.zfill(14) == ficha.gtin for g in gtins):
                raise serializers.ValidationError({'codigos_barra': 'Conserva el código consultado para asociar esta ficha externa.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        codigos_data = validated_data.pop('codigos_barra', [])
        ficha = validated_data.get('ficha_externa')
        if ficha:
            # Dos altas simultáneas del mismo GTIN comparten esta fila,
            # aunque un lector entregue EAN-13 y otro GTIN-14.
            ficha = FichaProductoExterna.objects.select_for_update().get(pk=ficha.pk)
            if productos_registrados(ficha.gtin):
                raise serializers.ValidationError({'codigos_barra': 'Este producto ya fue registrado. Búscalo en el catálogo para consultar o editar su información.'})
        producto = Producto.objects.create(**validated_data)

        for index, codigo_data in enumerate(codigos_data):
            if not any(item.get('es_principal') for item in codigos_data) and index == 0:
                codigo_data['es_principal'] = True
            CodigoBarra.objects.create(producto=producto, **codigo_data)

        return producto

    @transaction.atomic
    def update(self, instance, validated_data):
        codigos_data = validated_data.pop('codigos_barra', None)

        # Actualizar campos del producto
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Actualizar códigos si se enviaron
        if codigos_data is not None:
            # Conservar ID, tipo y fecha de los códigos que siguen presentes.
            existentes = {c.codigo: c for c in instance.codigos_barra.all()}
            instance.codigos_barra.exclude(codigo__in=[c['codigo'] for c in codigos_data]).delete()
            tiene_principal = any(c.get('es_principal') for c in codigos_data)
            for index, codigo_data in enumerate(codigos_data):
                if not tiene_principal:
                    codigo_data['es_principal'] = index == 0
                codigo = existentes.get(codigo_data['codigo'])
                if codigo is None:
                    CodigoBarra.objects.create(producto=instance, **codigo_data)
                else:
                    for attr, value in codigo_data.items():
                        setattr(codigo, attr, value)
                    codigo.save()

        instance._prefetched_objects_cache = {}

        return instance


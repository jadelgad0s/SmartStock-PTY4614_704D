--
-- PostgreSQL database dump
--

\restrict zdvzHWLvNE1bWmKU7qsgVISgq6fGBKupnZLa9fZrAWqiAdUUfZftadbQv1BUjAL

-- Dumped from database version 18.7 (a21afb5)
-- Dumped by pg_dump version 18.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: neon_auth; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA neon_auth;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: account; Type: TABLE; Schema: neon_auth; Owner: -
--

CREATE TABLE neon_auth.account (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    "accountId" text NOT NULL,
    "providerId" text NOT NULL,
    "userId" uuid NOT NULL,
    "accessToken" text,
    "refreshToken" text,
    "idToken" text,
    "accessTokenExpiresAt" timestamp with time zone,
    "refreshTokenExpiresAt" timestamp with time zone,
    scope text,
    password text,
    "createdAt" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp with time zone NOT NULL
);


--
-- Name: invitation; Type: TABLE; Schema: neon_auth; Owner: -
--

CREATE TABLE neon_auth.invitation (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    "organizationId" uuid NOT NULL,
    email text NOT NULL,
    role text,
    status text NOT NULL,
    "expiresAt" timestamp with time zone NOT NULL,
    "createdAt" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "inviterId" uuid NOT NULL
);


--
-- Name: jwks; Type: TABLE; Schema: neon_auth; Owner: -
--

CREATE TABLE neon_auth.jwks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    "publicKey" text NOT NULL,
    "privateKey" text NOT NULL,
    "createdAt" timestamp with time zone NOT NULL,
    "expiresAt" timestamp with time zone,
    alg text,
    crv text
);


--
-- Name: member; Type: TABLE; Schema: neon_auth; Owner: -
--

CREATE TABLE neon_auth.member (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    "organizationId" uuid NOT NULL,
    "userId" uuid NOT NULL,
    role text NOT NULL,
    "createdAt" timestamp with time zone NOT NULL
);


--
-- Name: organization; Type: TABLE; Schema: neon_auth; Owner: -
--

CREATE TABLE neon_auth.organization (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    logo text,
    "createdAt" timestamp with time zone NOT NULL,
    metadata text
);


--
-- Name: project_config; Type: TABLE; Schema: neon_auth; Owner: -
--

CREATE TABLE neon_auth.project_config (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    endpoint_id text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    trusted_origins jsonb NOT NULL,
    social_providers jsonb NOT NULL,
    email_provider jsonb,
    email_and_password jsonb,
    allow_localhost boolean NOT NULL,
    plugin_configs jsonb,
    webhook_config jsonb,
    auth_logs_export_enabled boolean DEFAULT false
);
ALTER TABLE ONLY neon_auth.project_config ALTER COLUMN auth_logs_export_enabled SET (pg_attver=62509160);


--
-- Name: session; Type: TABLE; Schema: neon_auth; Owner: -
--

CREATE TABLE neon_auth.session (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    "expiresAt" timestamp with time zone NOT NULL,
    token text NOT NULL,
    "createdAt" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp with time zone NOT NULL,
    "ipAddress" text,
    "userAgent" text,
    "userId" uuid NOT NULL,
    "impersonatedBy" text,
    "activeOrganizationId" text
);


--
-- Name: user; Type: TABLE; Schema: neon_auth; Owner: -
--

CREATE TABLE neon_auth."user" (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    email text NOT NULL,
    "emailVerified" boolean NOT NULL,
    image text,
    "createdAt" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    role text,
    banned boolean,
    "banReason" text,
    "banExpires" timestamp with time zone
);


--
-- Name: verification; Type: TABLE; Schema: neon_auth; Owner: -
--

CREATE TABLE neon_auth.verification (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    identifier text NOT NULL,
    value text NOT NULL,
    "expiresAt" timestamp with time zone NOT NULL,
    "createdAt" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "updatedAt" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: alertas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alertas (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    mensaje text NOT NULL,
    activa boolean NOT NULL,
    producto_id bigint NOT NULL,
    bodega_id bigint NOT NULL,
    tipo_id bigint NOT NULL
);


--
-- Name: alertas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.alertas ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.alertas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: auditoria; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auditoria (
    id bigint CONSTRAINT core_auditoria_id_not_null NOT NULL,
    fecha_creacion timestamp with time zone CONSTRAINT core_auditoria_fecha_creacion_not_null NOT NULL,
    fecha_modificacion timestamp with time zone CONSTRAINT core_auditoria_fecha_modificacion_not_null NOT NULL,
    accion character varying(20) CONSTRAINT core_auditoria_accion_not_null NOT NULL,
    modelo character varying(100) CONSTRAINT core_auditoria_modelo_not_null NOT NULL,
    objeto_id character varying(50) CONSTRAINT core_auditoria_objeto_id_not_null NOT NULL,
    descripcion text CONSTRAINT core_auditoria_descripcion_not_null NOT NULL,
    ip_address inet,
    user_agent text CONSTRAINT core_auditoria_user_agent_not_null NOT NULL,
    usuario_id bigint
);


--
-- Name: auth_group; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_group (
    id integer NOT NULL,
    name character varying(150) NOT NULL
);


--
-- Name: auth_group_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.auth_group ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.auth_group_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: auth_group_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_group_permissions (
    id bigint NOT NULL,
    group_id integer NOT NULL,
    permission_id integer NOT NULL
);


--
-- Name: auth_group_permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.auth_group_permissions ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.auth_group_permissions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: auth_permission; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_permission (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    content_type_id integer NOT NULL,
    codename character varying(100) NOT NULL
);


--
-- Name: auth_permission_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.auth_permission ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.auth_permission_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: bodegas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bodegas (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    nombre character varying(100) NOT NULL,
    direccion character varying(200) NOT NULL,
    activa boolean NOT NULL
);


--
-- Name: bodegas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.bodegas ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.bodegas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: codigos_barra; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.codigos_barra (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    codigo character varying(100) NOT NULL,
    tipo character varying(10) NOT NULL,
    es_principal boolean NOT NULL,
    producto_id bigint NOT NULL
);


--
-- Name: codigos_barra_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.codigos_barra ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.codigos_barra_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: core_auditoria_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.auditoria ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.core_auditoria_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: cupos_consulta_externa; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cupos_consulta_externa (
    proveedor character varying(40) NOT NULL,
    intentos jsonb NOT NULL,
    bloqueado_hasta timestamp with time zone
);


--
-- Name: detalle_movimiento; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.detalle_movimiento (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    cantidad integer NOT NULL,
    producto_id bigint NOT NULL,
    movimiento_id bigint NOT NULL,
    CONSTRAINT detalle_mov_cantidad_rango CHECK (((cantidad >= 1) AND (cantidad <= 2147483647)))
);


--
-- Name: detalle_movimiento_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.detalle_movimiento ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.detalle_movimiento_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: detalle_transferencia; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.detalle_transferencia (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    cantidad integer NOT NULL,
    producto_id bigint NOT NULL,
    transferencia_id bigint NOT NULL,
    CONSTRAINT detalle_transfer_cantidad_rango CHECK (((cantidad >= 1) AND (cantidad <= 2147483647)))
);


--
-- Name: detalle_transferencia_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.detalle_transferencia ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.detalle_transferencia_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: django_admin_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.django_admin_log (
    id integer NOT NULL,
    action_time timestamp with time zone NOT NULL,
    object_id text,
    object_repr character varying(200) NOT NULL,
    action_flag smallint NOT NULL,
    change_message text NOT NULL,
    content_type_id integer,
    user_id bigint NOT NULL,
    CONSTRAINT django_admin_log_action_flag_check CHECK ((action_flag >= 0))
);


--
-- Name: django_admin_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.django_admin_log ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.django_admin_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: django_content_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.django_content_type (
    id integer NOT NULL,
    app_label character varying(100) NOT NULL,
    model character varying(100) NOT NULL
);


--
-- Name: django_content_type_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.django_content_type ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.django_content_type_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: django_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.django_migrations (
    id bigint NOT NULL,
    app character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    applied timestamp with time zone NOT NULL
);


--
-- Name: django_migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.django_migrations ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.django_migrations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: django_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.django_session (
    session_key character varying(40) NOT NULL,
    session_data text NOT NULL,
    expire_date timestamp with time zone NOT NULL
);


--
-- Name: envios_alertas_sms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.envios_alertas_sms (
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    ciclo uuid NOT NULL,
    nivel smallint NOT NULL,
    sku character varying(50) NOT NULL,
    producto_nombre character varying(200) NOT NULL,
    bodega_nombre character varying(100) NOT NULL,
    cantidad integer NOT NULL,
    minimo integer NOT NULL,
    destinatario character varying(16) NOT NULL,
    mensaje character varying(160) NOT NULL,
    estado character varying(20) NOT NULL,
    intentos smallint NOT NULL,
    ultimo_intento timestamp with time zone,
    proximo_intento timestamp with time zone,
    twilio_sid character varying(34),
    codigo_error character varying(12) NOT NULL,
    detalle character varying(200) NOT NULL,
    bodega_id bigint,
    producto_id bigint,
    CONSTRAINT envios_alertas_sms_intentos_check CHECK ((intentos >= 0)),
    CONSTRAINT envios_alertas_sms_nivel_check CHECK ((nivel >= 0))
);


--
-- Name: estado_stock_sms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.estado_stock_sms (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    ciclo uuid NOT NULL,
    nivel_maximo smallint NOT NULL,
    bodega_id bigint NOT NULL,
    producto_id bigint NOT NULL,
    CONSTRAINT estado_stock_sms_nivel_maximo_check CHECK ((nivel_maximo >= 0))
);


--
-- Name: estado_stock_sms_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.estado_stock_sms ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.estado_stock_sms_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: estanterias; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.estanterias (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    codigo character varying(20) NOT NULL,
    pasillo_id bigint NOT NULL
);


--
-- Name: estanterias_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.estanterias ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.estanterias_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: fichas_producto_externas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fichas_producto_externas (
    id bigint NOT NULL,
    gtin character varying(14) NOT NULL,
    datos jsonb NOT NULL,
    vence timestamp with time zone NOT NULL,
    fecha_consulta timestamp with time zone NOT NULL
);


--
-- Name: fichas_producto_externas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.fichas_producto_externas ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.fichas_producto_externas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: historial_movimientos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.historial_movimientos (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    tipo_registro character varying(50) NOT NULL,
    registro_id integer NOT NULL,
    descripcion text NOT NULL,
    producto_id bigint NOT NULL
);


--
-- Name: historial_movimientos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.historial_movimientos ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.historial_movimientos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: limite_diario_sms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.limite_diario_sms (
    id bigint NOT NULL,
    fecha date NOT NULL,
    intentos integer NOT NULL,
    CONSTRAINT limite_diario_sms_intentos_check CHECK ((intentos >= 0))
);


--
-- Name: limite_diario_sms_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.limite_diario_sms ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.limite_diario_sms_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: log_alertas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.log_alertas (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    accion character varying(100) NOT NULL,
    alerta_id bigint NOT NULL,
    usuario_id bigint
);


--
-- Name: log_alertas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.log_alertas ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.log_alertas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: mermas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mermas (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    cantidad integer NOT NULL,
    bodega_id bigint NOT NULL,
    producto_id bigint NOT NULL,
    usuario_id bigint NOT NULL,
    motivo_id bigint NOT NULL,
    observacion text NOT NULL,
    CONSTRAINT merma_cantidad_rango CHECK (((cantidad >= 1) AND (cantidad <= 2147483647)))
);


--
-- Name: mermas_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.mermas ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.mermas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: motivo_merma; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.motivo_merma (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    descripcion character varying(100) NOT NULL
);


--
-- Name: motivo_merma_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.motivo_merma ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.motivo_merma_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: movimientos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.movimientos (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    documento_referencia character varying(100) NOT NULL,
    bodega_id bigint NOT NULL,
    usuario_id bigint NOT NULL,
    tipo_id bigint NOT NULL
);


--
-- Name: movimientos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.movimientos ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.movimientos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: niveles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.niveles (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    codigo character varying(20) NOT NULL,
    estanteria_id bigint NOT NULL
);


--
-- Name: niveles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.niveles ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.niveles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: notificaciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notificaciones (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    tipo character varying(20) NOT NULL,
    titulo character varying(150) NOT NULL,
    mensaje text NOT NULL,
    link character varying(200) NOT NULL,
    leida boolean NOT NULL,
    usuario_destino_id bigint NOT NULL
);


--
-- Name: notificaciones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.notificaciones ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.notificaciones_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: pasillos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pasillos (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    codigo character varying(20) NOT NULL,
    bodega_id bigint NOT NULL
);


--
-- Name: pasillos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.pasillos ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.pasillos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: permisos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.permisos (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    codigo character varying(100) NOT NULL,
    nombre character varying(150) NOT NULL,
    descripcion text NOT NULL,
    modulo character varying(50) NOT NULL
);


--
-- Name: permisos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.permisos ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.permisos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: producto_ubicacion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.producto_ubicacion (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    cantidad integer NOT NULL,
    producto_id bigint NOT NULL,
    ubicacion_id bigint NOT NULL
);


--
-- Name: producto_ubicacion_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.producto_ubicacion ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.producto_ubicacion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: productos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.productos (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    activo boolean NOT NULL,
    sku character varying(50) NOT NULL,
    nombre character varying(200) NOT NULL,
    descripcion text NOT NULL,
    precio_referencia numeric(12,2) NOT NULL,
    imagen character varying(100),
    ficha_externa_id bigint
);


--
-- Name: productos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.productos ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.productos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: reportes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reportes (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    archivo character varying(100) NOT NULL,
    parametros jsonb,
    usuario_id bigint,
    tipo_id bigint NOT NULL
);


--
-- Name: reportes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.reportes ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.reportes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: rol_permiso; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rol_permiso (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    permiso_id bigint NOT NULL,
    rol_id bigint NOT NULL
);


--
-- Name: rol_permiso_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.rol_permiso ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.rol_permiso_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    activo boolean NOT NULL,
    nombre character varying(50) NOT NULL,
    codigo character varying(50) NOT NULL,
    descripcion text NOT NULL,
    es_sistema boolean NOT NULL
);


--
-- Name: roles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.roles ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.roles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: sesiones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sesiones (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    token_jti character varying(255) NOT NULL,
    ip_address inet,
    user_agent text NOT NULL,
    activa boolean NOT NULL,
    fecha_expiracion timestamp with time zone NOT NULL,
    usuario_id bigint NOT NULL
);


--
-- Name: sesiones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.sesiones ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.sesiones_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: stock_bodega; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stock_bodega (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    cantidad_total integer NOT NULL,
    bodega_id bigint NOT NULL,
    producto_id bigint NOT NULL,
    CONSTRAINT stock_cantidad_rango CHECK (((cantidad_total >= 0) AND (cantidad_total <= 2147483647)))
);


--
-- Name: stock_bodega_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.stock_bodega ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.stock_bodega_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: stock_minimo; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stock_minimo (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    cantidad_minima integer NOT NULL,
    bodega_id bigint NOT NULL,
    producto_id bigint NOT NULL,
    CONSTRAINT minimo_cantidad_rango CHECK (((cantidad_minima >= 0) AND (cantidad_minima <= 2147483647)))
);


--
-- Name: stock_minimo_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.stock_minimo ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.stock_minimo_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: tipo_alerta; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tipo_alerta (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    nombre character varying(50) NOT NULL,
    nivel_gravedad integer NOT NULL
);


--
-- Name: tipo_alerta_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.tipo_alerta ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.tipo_alerta_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: tipo_movimiento; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tipo_movimiento (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    nombre character varying(50) NOT NULL,
    operacion character varying(1) NOT NULL
);


--
-- Name: tipo_movimiento_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.tipo_movimiento ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.tipo_movimiento_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: tipo_reporte; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tipo_reporte (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    nombre character varying(50) NOT NULL,
    formato character varying(10) NOT NULL
);


--
-- Name: tipo_reporte_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.tipo_reporte ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.tipo_reporte_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: token_blacklist_blacklistedtoken; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.token_blacklist_blacklistedtoken (
    id bigint NOT NULL,
    blacklisted_at timestamp with time zone NOT NULL,
    token_id bigint NOT NULL
);


--
-- Name: token_blacklist_blacklistedtoken_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.token_blacklist_blacklistedtoken ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.token_blacklist_blacklistedtoken_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: token_blacklist_outstandingtoken; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.token_blacklist_outstandingtoken (
    id bigint NOT NULL,
    token text NOT NULL,
    created_at timestamp with time zone,
    expires_at timestamp with time zone NOT NULL,
    user_id bigint,
    jti character varying(255) CONSTRAINT token_blacklist_outstandingtoken_jti_hex_not_null NOT NULL
);


--
-- Name: token_blacklist_outstandingtoken_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.token_blacklist_outstandingtoken ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.token_blacklist_outstandingtoken_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: transferencias; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.transferencias (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    estado character varying(20) NOT NULL,
    bodega_destino_id bigint NOT NULL,
    bodega_origen_id bigint NOT NULL,
    usuario_id bigint NOT NULL
);


--
-- Name: transferencias_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.transferencias ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.transferencias_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: ubicaciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ubicaciones (
    id bigint NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    codigo character varying(20) NOT NULL,
    capacidad_maxima integer NOT NULL,
    nivel_id bigint NOT NULL
);


--
-- Name: ubicaciones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.ubicaciones ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.ubicaciones_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: usuarios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.usuarios (
    id bigint NOT NULL,
    password character varying(128) NOT NULL,
    last_login timestamp with time zone,
    is_superuser boolean NOT NULL,
    fecha_creacion timestamp with time zone NOT NULL,
    fecha_modificacion timestamp with time zone NOT NULL,
    activo boolean NOT NULL,
    email character varying(254) NOT NULL,
    nombres character varying(100) NOT NULL,
    apellidos character varying(100) NOT NULL,
    telefono character varying(20) NOT NULL,
    ultimo_login timestamp with time zone,
    intentos_fallidos integer NOT NULL,
    bloqueado_hasta timestamp with time zone,
    is_staff boolean NOT NULL,
    rol_id bigint,
    CONSTRAINT usuarios_intentos_fallidos_check CHECK ((intentos_fallidos >= 0))
);


--
-- Name: usuarios_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.usuarios_groups (
    id bigint NOT NULL,
    usuario_id bigint NOT NULL,
    group_id integer NOT NULL
);


--
-- Name: usuarios_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.usuarios_groups ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.usuarios_groups_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: usuarios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.usuarios ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.usuarios_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: usuarios_user_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.usuarios_user_permissions (
    id bigint NOT NULL,
    usuario_id bigint NOT NULL,
    permission_id integer NOT NULL
);


--
-- Name: usuarios_user_permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.usuarios_user_permissions ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.usuarios_user_permissions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: account account_pkey; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.account
    ADD CONSTRAINT account_pkey PRIMARY KEY (id);


--
-- Name: invitation invitation_pkey; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.invitation
    ADD CONSTRAINT invitation_pkey PRIMARY KEY (id);


--
-- Name: jwks jwks_pkey; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.jwks
    ADD CONSTRAINT jwks_pkey PRIMARY KEY (id);


--
-- Name: member member_pkey; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.member
    ADD CONSTRAINT member_pkey PRIMARY KEY (id);


--
-- Name: organization organization_pkey; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.organization
    ADD CONSTRAINT organization_pkey PRIMARY KEY (id);


--
-- Name: organization organization_slug_key; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.organization
    ADD CONSTRAINT organization_slug_key UNIQUE (slug);


--
-- Name: project_config project_config_endpoint_id_key; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.project_config
    ADD CONSTRAINT project_config_endpoint_id_key UNIQUE (endpoint_id);


--
-- Name: project_config project_config_pkey; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.project_config
    ADD CONSTRAINT project_config_pkey PRIMARY KEY (id);


--
-- Name: session session_pkey; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.session
    ADD CONSTRAINT session_pkey PRIMARY KEY (id);


--
-- Name: session session_token_key; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.session
    ADD CONSTRAINT session_token_key UNIQUE (token);


--
-- Name: user user_email_key; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth."user"
    ADD CONSTRAINT user_email_key UNIQUE (email);


--
-- Name: user user_pkey; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth."user"
    ADD CONSTRAINT user_pkey PRIMARY KEY (id);


--
-- Name: verification verification_pkey; Type: CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.verification
    ADD CONSTRAINT verification_pkey PRIMARY KEY (id);


--
-- Name: alertas alertas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_pkey PRIMARY KEY (id);


--
-- Name: auth_group auth_group_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_group
    ADD CONSTRAINT auth_group_name_key UNIQUE (name);


--
-- Name: auth_group_permissions auth_group_permissions_group_id_permission_id_0cd325b0_uniq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissions_group_id_permission_id_0cd325b0_uniq UNIQUE (group_id, permission_id);


--
-- Name: auth_group_permissions auth_group_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissions_pkey PRIMARY KEY (id);


--
-- Name: auth_group auth_group_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_group
    ADD CONSTRAINT auth_group_pkey PRIMARY KEY (id);


--
-- Name: auth_permission auth_permission_content_type_id_codename_01ab375a_uniq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_permission
    ADD CONSTRAINT auth_permission_content_type_id_codename_01ab375a_uniq UNIQUE (content_type_id, codename);


--
-- Name: auth_permission auth_permission_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_permission
    ADD CONSTRAINT auth_permission_pkey PRIMARY KEY (id);


--
-- Name: bodegas bodegas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bodegas
    ADD CONSTRAINT bodegas_pkey PRIMARY KEY (id);


--
-- Name: codigos_barra codigos_barra_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.codigos_barra
    ADD CONSTRAINT codigos_barra_codigo_key UNIQUE (codigo);


--
-- Name: codigos_barra codigos_barra_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.codigos_barra
    ADD CONSTRAINT codigos_barra_pkey PRIMARY KEY (id);


--
-- Name: auditoria core_auditoria_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auditoria
    ADD CONSTRAINT core_auditoria_pkey PRIMARY KEY (id);


--
-- Name: cupos_consulta_externa cupos_consulta_externa_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cupos_consulta_externa
    ADD CONSTRAINT cupos_consulta_externa_pkey PRIMARY KEY (proveedor);


--
-- Name: detalle_movimiento detalle_movimiento_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detalle_movimiento
    ADD CONSTRAINT detalle_movimiento_pkey PRIMARY KEY (id);


--
-- Name: detalle_transferencia detalle_transferencia_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detalle_transferencia
    ADD CONSTRAINT detalle_transferencia_pkey PRIMARY KEY (id);


--
-- Name: django_admin_log django_admin_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_admin_log
    ADD CONSTRAINT django_admin_log_pkey PRIMARY KEY (id);


--
-- Name: django_content_type django_content_type_app_label_model_76bd3d3b_uniq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_content_type
    ADD CONSTRAINT django_content_type_app_label_model_76bd3d3b_uniq UNIQUE (app_label, model);


--
-- Name: django_content_type django_content_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_content_type
    ADD CONSTRAINT django_content_type_pkey PRIMARY KEY (id);


--
-- Name: django_migrations django_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_migrations
    ADD CONSTRAINT django_migrations_pkey PRIMARY KEY (id);


--
-- Name: django_session django_session_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_session
    ADD CONSTRAINT django_session_pkey PRIMARY KEY (session_key);


--
-- Name: envios_alertas_sms envios_alertas_sms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.envios_alertas_sms
    ADD CONSTRAINT envios_alertas_sms_pkey PRIMARY KEY (id);


--
-- Name: envios_alertas_sms envios_alertas_sms_twilio_sid_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.envios_alertas_sms
    ADD CONSTRAINT envios_alertas_sms_twilio_sid_key UNIQUE (twilio_sid);


--
-- Name: estado_stock_sms estado_stock_sms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.estado_stock_sms
    ADD CONSTRAINT estado_stock_sms_pkey PRIMARY KEY (id);


--
-- Name: estanterias estanterias_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.estanterias
    ADD CONSTRAINT estanterias_pkey PRIMARY KEY (id);


--
-- Name: fichas_producto_externas fichas_producto_externas_gtin_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fichas_producto_externas
    ADD CONSTRAINT fichas_producto_externas_gtin_key UNIQUE (gtin);


--
-- Name: fichas_producto_externas fichas_producto_externas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fichas_producto_externas
    ADD CONSTRAINT fichas_producto_externas_pkey PRIMARY KEY (id);


--
-- Name: historial_movimientos historial_movimientos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historial_movimientos
    ADD CONSTRAINT historial_movimientos_pkey PRIMARY KEY (id);


--
-- Name: limite_diario_sms limite_diario_sms_fecha_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.limite_diario_sms
    ADD CONSTRAINT limite_diario_sms_fecha_key UNIQUE (fecha);


--
-- Name: limite_diario_sms limite_diario_sms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.limite_diario_sms
    ADD CONSTRAINT limite_diario_sms_pkey PRIMARY KEY (id);


--
-- Name: log_alertas log_alertas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.log_alertas
    ADD CONSTRAINT log_alertas_pkey PRIMARY KEY (id);


--
-- Name: mermas mermas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mermas
    ADD CONSTRAINT mermas_pkey PRIMARY KEY (id);


--
-- Name: stock_minimo minimo_producto_bodega_unico; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_minimo
    ADD CONSTRAINT minimo_producto_bodega_unico UNIQUE (producto_id, bodega_id);


--
-- Name: motivo_merma motivo_merma_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.motivo_merma
    ADD CONSTRAINT motivo_merma_pkey PRIMARY KEY (id);


--
-- Name: movimientos movimientos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.movimientos
    ADD CONSTRAINT movimientos_pkey PRIMARY KEY (id);


--
-- Name: niveles niveles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.niveles
    ADD CONSTRAINT niveles_pkey PRIMARY KEY (id);


--
-- Name: notificaciones notificaciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notificaciones
    ADD CONSTRAINT notificaciones_pkey PRIMARY KEY (id);


--
-- Name: pasillos pasillos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pasillos
    ADD CONSTRAINT pasillos_pkey PRIMARY KEY (id);


--
-- Name: permisos permisos_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permisos
    ADD CONSTRAINT permisos_codigo_key UNIQUE (codigo);


--
-- Name: permisos permisos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permisos
    ADD CONSTRAINT permisos_pkey PRIMARY KEY (id);


--
-- Name: producto_ubicacion producto_ubicacion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.producto_ubicacion
    ADD CONSTRAINT producto_ubicacion_pkey PRIMARY KEY (id);


--
-- Name: productos productos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.productos
    ADD CONSTRAINT productos_pkey PRIMARY KEY (id);


--
-- Name: productos productos_sku_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.productos
    ADD CONSTRAINT productos_sku_key UNIQUE (sku);


--
-- Name: reportes reportes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reportes
    ADD CONSTRAINT reportes_pkey PRIMARY KEY (id);


--
-- Name: rol_permiso rol_permiso_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rol_permiso
    ADD CONSTRAINT rol_permiso_pkey PRIMARY KEY (id);


--
-- Name: rol_permiso rol_permiso_rol_id_permiso_id_3db570a7_uniq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rol_permiso
    ADD CONSTRAINT rol_permiso_rol_id_permiso_id_3db570a7_uniq UNIQUE (rol_id, permiso_id);


--
-- Name: roles roles_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_codigo_key UNIQUE (codigo);


--
-- Name: roles roles_nombre_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_nombre_key UNIQUE (nombre);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: sesiones sesiones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sesiones
    ADD CONSTRAINT sesiones_pkey PRIMARY KEY (id);


--
-- Name: sesiones sesiones_token_jti_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sesiones
    ADD CONSTRAINT sesiones_token_jti_key UNIQUE (token_jti);


--
-- Name: estado_stock_sms sms_estado_producto_bodega; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.estado_stock_sms
    ADD CONSTRAINT sms_estado_producto_bodega UNIQUE (producto_id, bodega_id);


--
-- Name: envios_alertas_sms sms_un_envio_por_nivel_ciclo; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.envios_alertas_sms
    ADD CONSTRAINT sms_un_envio_por_nivel_ciclo UNIQUE (ciclo, nivel, destinatario);


--
-- Name: stock_bodega stock_bodega_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_bodega
    ADD CONSTRAINT stock_bodega_pkey PRIMARY KEY (id);


--
-- Name: stock_minimo stock_minimo_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_minimo
    ADD CONSTRAINT stock_minimo_pkey PRIMARY KEY (id);


--
-- Name: stock_bodega stock_producto_bodega_unico; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_bodega
    ADD CONSTRAINT stock_producto_bodega_unico UNIQUE (producto_id, bodega_id);


--
-- Name: tipo_alerta tipo_alerta_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tipo_alerta
    ADD CONSTRAINT tipo_alerta_pkey PRIMARY KEY (id);


--
-- Name: tipo_movimiento tipo_movimiento_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tipo_movimiento
    ADD CONSTRAINT tipo_movimiento_pkey PRIMARY KEY (id);


--
-- Name: tipo_reporte tipo_reporte_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tipo_reporte
    ADD CONSTRAINT tipo_reporte_pkey PRIMARY KEY (id);


--
-- Name: token_blacklist_blacklistedtoken token_blacklist_blacklistedtoken_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.token_blacklist_blacklistedtoken
    ADD CONSTRAINT token_blacklist_blacklistedtoken_pkey PRIMARY KEY (id);


--
-- Name: token_blacklist_blacklistedtoken token_blacklist_blacklistedtoken_token_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.token_blacklist_blacklistedtoken
    ADD CONSTRAINT token_blacklist_blacklistedtoken_token_id_key UNIQUE (token_id);


--
-- Name: token_blacklist_outstandingtoken token_blacklist_outstandingtoken_jti_hex_d9bdf6f7_uniq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.token_blacklist_outstandingtoken
    ADD CONSTRAINT token_blacklist_outstandingtoken_jti_hex_d9bdf6f7_uniq UNIQUE (jti);


--
-- Name: token_blacklist_outstandingtoken token_blacklist_outstandingtoken_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.token_blacklist_outstandingtoken
    ADD CONSTRAINT token_blacklist_outstandingtoken_pkey PRIMARY KEY (id);


--
-- Name: transferencias transferencias_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transferencias
    ADD CONSTRAINT transferencias_pkey PRIMARY KEY (id);


--
-- Name: ubicaciones ubicaciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ubicaciones
    ADD CONSTRAINT ubicaciones_pkey PRIMARY KEY (id);


--
-- Name: usuarios usuarios_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_email_key UNIQUE (email);


--
-- Name: usuarios_groups usuarios_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios_groups
    ADD CONSTRAINT usuarios_groups_pkey PRIMARY KEY (id);


--
-- Name: usuarios_groups usuarios_groups_usuario_id_group_id_a66c5ef3_uniq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios_groups
    ADD CONSTRAINT usuarios_groups_usuario_id_group_id_a66c5ef3_uniq UNIQUE (usuario_id, group_id);


--
-- Name: usuarios usuarios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_pkey PRIMARY KEY (id);


--
-- Name: usuarios_user_permissions usuarios_user_permission_usuario_id_permission_id_474b33a5_uniq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios_user_permissions
    ADD CONSTRAINT usuarios_user_permission_usuario_id_permission_id_474b33a5_uniq UNIQUE (usuario_id, permission_id);


--
-- Name: usuarios_user_permissions usuarios_user_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios_user_permissions
    ADD CONSTRAINT usuarios_user_permissions_pkey PRIMARY KEY (id);


--
-- Name: account_userId_idx; Type: INDEX; Schema: neon_auth; Owner: -
--

CREATE INDEX "account_userId_idx" ON neon_auth.account USING btree ("userId");


--
-- Name: invitation_email_idx; Type: INDEX; Schema: neon_auth; Owner: -
--

CREATE INDEX invitation_email_idx ON neon_auth.invitation USING btree (email);


--
-- Name: invitation_organizationId_idx; Type: INDEX; Schema: neon_auth; Owner: -
--

CREATE INDEX "invitation_organizationId_idx" ON neon_auth.invitation USING btree ("organizationId");


--
-- Name: member_organizationId_idx; Type: INDEX; Schema: neon_auth; Owner: -
--

CREATE INDEX "member_organizationId_idx" ON neon_auth.member USING btree ("organizationId");


--
-- Name: member_userId_idx; Type: INDEX; Schema: neon_auth; Owner: -
--

CREATE INDEX "member_userId_idx" ON neon_auth.member USING btree ("userId");


--
-- Name: session_userId_idx; Type: INDEX; Schema: neon_auth; Owner: -
--

CREATE INDEX "session_userId_idx" ON neon_auth.session USING btree ("userId");


--
-- Name: verification_identifier_idx; Type: INDEX; Schema: neon_auth; Owner: -
--

CREATE INDEX verification_identifier_idx ON neon_auth.verification USING btree (identifier);


--
-- Name: alertas_bodega_id_d74cdf90; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alertas_bodega_id_d74cdf90 ON public.alertas USING btree (bodega_id);


--
-- Name: alertas_producto_id_61fe568d; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alertas_producto_id_61fe568d ON public.alertas USING btree (producto_id);


--
-- Name: alertas_tipo_id_7fe22092; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alertas_tipo_id_7fe22092 ON public.alertas USING btree (tipo_id);


--
-- Name: auth_group_name_a6ea08ec_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX auth_group_name_a6ea08ec_like ON public.auth_group USING btree (name varchar_pattern_ops);


--
-- Name: auth_group_permissions_group_id_b120cbf9; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX auth_group_permissions_group_id_b120cbf9 ON public.auth_group_permissions USING btree (group_id);


--
-- Name: auth_group_permissions_permission_id_84c5c92e; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX auth_group_permissions_permission_id_84c5c92e ON public.auth_group_permissions USING btree (permission_id);


--
-- Name: auth_permission_content_type_id_2f476e4b; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX auth_permission_content_type_id_2f476e4b ON public.auth_permission USING btree (content_type_id);


--
-- Name: codigos_barra_codigo_cf0e3df7_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX codigos_barra_codigo_cf0e3df7_like ON public.codigos_barra USING btree (codigo varchar_pattern_ops);


--
-- Name: codigos_barra_producto_id_30897e80; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX codigos_barra_producto_id_30897e80 ON public.codigos_barra USING btree (producto_id);


--
-- Name: core_auditoria_usuario_id_124e9f95; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX core_auditoria_usuario_id_124e9f95 ON public.auditoria USING btree (usuario_id);


--
-- Name: cupos_consulta_externa_proveedor_06051731_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX cupos_consulta_externa_proveedor_06051731_like ON public.cupos_consulta_externa USING btree (proveedor varchar_pattern_ops);


--
-- Name: detalle_movimiento_movimiento_id_0cc24a90; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX detalle_movimiento_movimiento_id_0cc24a90 ON public.detalle_movimiento USING btree (movimiento_id);


--
-- Name: detalle_movimiento_producto_id_96c53934; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX detalle_movimiento_producto_id_96c53934 ON public.detalle_movimiento USING btree (producto_id);


--
-- Name: detalle_transferencia_producto_id_dece154d; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX detalle_transferencia_producto_id_dece154d ON public.detalle_transferencia USING btree (producto_id);


--
-- Name: detalle_transferencia_transferencia_id_9067972d; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX detalle_transferencia_transferencia_id_9067972d ON public.detalle_transferencia USING btree (transferencia_id);


--
-- Name: django_admin_log_content_type_id_c4bce8eb; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX django_admin_log_content_type_id_c4bce8eb ON public.django_admin_log USING btree (content_type_id);


--
-- Name: django_admin_log_user_id_c564eba6; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX django_admin_log_user_id_c564eba6 ON public.django_admin_log USING btree (user_id);


--
-- Name: django_session_expire_date_a5c62663; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX django_session_expire_date_a5c62663 ON public.django_session USING btree (expire_date);


--
-- Name: django_session_session_key_c0390e0f_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX django_session_session_key_c0390e0f_like ON public.django_session USING btree (session_key varchar_pattern_ops);


--
-- Name: envios_alertas_sms_bodega_id_19d5e198; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX envios_alertas_sms_bodega_id_19d5e198 ON public.envios_alertas_sms USING btree (bodega_id);


--
-- Name: envios_alertas_sms_estado_2d94b7c0; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX envios_alertas_sms_estado_2d94b7c0 ON public.envios_alertas_sms USING btree (estado);


--
-- Name: envios_alertas_sms_estado_2d94b7c0_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX envios_alertas_sms_estado_2d94b7c0_like ON public.envios_alertas_sms USING btree (estado varchar_pattern_ops);


--
-- Name: envios_alertas_sms_producto_id_7a718ae5; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX envios_alertas_sms_producto_id_7a718ae5 ON public.envios_alertas_sms USING btree (producto_id);


--
-- Name: envios_alertas_sms_twilio_sid_f433fcc6_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX envios_alertas_sms_twilio_sid_f433fcc6_like ON public.envios_alertas_sms USING btree (twilio_sid varchar_pattern_ops);


--
-- Name: estado_stock_sms_bodega_id_59b10898; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX estado_stock_sms_bodega_id_59b10898 ON public.estado_stock_sms USING btree (bodega_id);


--
-- Name: estado_stock_sms_producto_id_e10f02a6; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX estado_stock_sms_producto_id_e10f02a6 ON public.estado_stock_sms USING btree (producto_id);


--
-- Name: estanterias_pasillo_id_d20195ea; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX estanterias_pasillo_id_d20195ea ON public.estanterias USING btree (pasillo_id);


--
-- Name: fichas_producto_externas_gtin_ff15cb35_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX fichas_producto_externas_gtin_ff15cb35_like ON public.fichas_producto_externas USING btree (gtin varchar_pattern_ops);


--
-- Name: fichas_producto_externas_vence_7207d3d3; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX fichas_producto_externas_vence_7207d3d3 ON public.fichas_producto_externas USING btree (vence);


--
-- Name: historial_movimientos_producto_id_b842760b; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX historial_movimientos_producto_id_b842760b ON public.historial_movimientos USING btree (producto_id);


--
-- Name: log_alertas_alerta_id_ca6f9a28; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX log_alertas_alerta_id_ca6f9a28 ON public.log_alertas USING btree (alerta_id);


--
-- Name: log_alertas_usuario_id_6a7d481e; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX log_alertas_usuario_id_6a7d481e ON public.log_alertas USING btree (usuario_id);


--
-- Name: mermas_bodega_id_e72d471d; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX mermas_bodega_id_e72d471d ON public.mermas USING btree (bodega_id);


--
-- Name: mermas_motivo_id_e94f2ce0; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX mermas_motivo_id_e94f2ce0 ON public.mermas USING btree (motivo_id);


--
-- Name: mermas_producto_id_c32a1cd0; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX mermas_producto_id_c32a1cd0 ON public.mermas USING btree (producto_id);


--
-- Name: mermas_usuario_id_4773ed89; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX mermas_usuario_id_4773ed89 ON public.mermas USING btree (usuario_id);


--
-- Name: movimientos_bodega_id_682f4e93; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX movimientos_bodega_id_682f4e93 ON public.movimientos USING btree (bodega_id);


--
-- Name: movimientos_tipo_id_ace2a658; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX movimientos_tipo_id_ace2a658 ON public.movimientos USING btree (tipo_id);


--
-- Name: movimientos_usuario_id_b1414a4b; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX movimientos_usuario_id_b1414a4b ON public.movimientos USING btree (usuario_id);


--
-- Name: niveles_estanteria_id_7afcb597; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX niveles_estanteria_id_7afcb597 ON public.niveles USING btree (estanteria_id);


--
-- Name: notificaciones_leida_11c2074f; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX notificaciones_leida_11c2074f ON public.notificaciones USING btree (leida);


--
-- Name: notificaciones_usuario_destino_id_9821f7d5; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX notificaciones_usuario_destino_id_9821f7d5 ON public.notificaciones USING btree (usuario_destino_id);


--
-- Name: pasillos_bodega_id_386dc501; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX pasillos_bodega_id_386dc501 ON public.pasillos USING btree (bodega_id);


--
-- Name: permisos_codigo_e85246ff_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX permisos_codigo_e85246ff_like ON public.permisos USING btree (codigo varchar_pattern_ops);


--
-- Name: permisos_modulo_8b3fce0e; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX permisos_modulo_8b3fce0e ON public.permisos USING btree (modulo);


--
-- Name: permisos_modulo_8b3fce0e_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX permisos_modulo_8b3fce0e_like ON public.permisos USING btree (modulo varchar_pattern_ops);


--
-- Name: producto_ubicacion_producto_id_74d5aaa9; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX producto_ubicacion_producto_id_74d5aaa9 ON public.producto_ubicacion USING btree (producto_id);


--
-- Name: producto_ubicacion_ubicacion_id_86be175a; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX producto_ubicacion_ubicacion_id_86be175a ON public.producto_ubicacion USING btree (ubicacion_id);


--
-- Name: productos_ficha_externa_id_910e0805; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX productos_ficha_externa_id_910e0805 ON public.productos USING btree (ficha_externa_id);


--
-- Name: productos_nombre_a8c23bc4; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX productos_nombre_a8c23bc4 ON public.productos USING btree (nombre);


--
-- Name: productos_nombre_a8c23bc4_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX productos_nombre_a8c23bc4_like ON public.productos USING btree (nombre varchar_pattern_ops);


--
-- Name: productos_sku_efc231bb_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX productos_sku_efc231bb_like ON public.productos USING btree (sku varchar_pattern_ops);


--
-- Name: reportes_tipo_id_6eb23b1c; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX reportes_tipo_id_6eb23b1c ON public.reportes USING btree (tipo_id);


--
-- Name: reportes_usuario_id_618c502b; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX reportes_usuario_id_618c502b ON public.reportes USING btree (usuario_id);


--
-- Name: rol_permiso_permiso_id_45298b7d; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rol_permiso_permiso_id_45298b7d ON public.rol_permiso USING btree (permiso_id);


--
-- Name: rol_permiso_rol_id_b275ea9d; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX rol_permiso_rol_id_b275ea9d ON public.rol_permiso USING btree (rol_id);


--
-- Name: roles_codigo_64af986f_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX roles_codigo_64af986f_like ON public.roles USING btree (codigo varchar_pattern_ops);


--
-- Name: roles_nombre_8cc26a1b_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX roles_nombre_8cc26a1b_like ON public.roles USING btree (nombre varchar_pattern_ops);


--
-- Name: sesiones_token_jti_f4cdfb66_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sesiones_token_jti_f4cdfb66_like ON public.sesiones USING btree (token_jti varchar_pattern_ops);


--
-- Name: sesiones_usuario_id_caef39af; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sesiones_usuario_id_caef39af ON public.sesiones USING btree (usuario_id);


--
-- Name: stock_bodega_bodega_id_be346900; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX stock_bodega_bodega_id_be346900 ON public.stock_bodega USING btree (bodega_id);


--
-- Name: stock_bodega_producto_id_5086e50b; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX stock_bodega_producto_id_5086e50b ON public.stock_bodega USING btree (producto_id);


--
-- Name: stock_minimo_bodega_id_6cc5cfd5; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX stock_minimo_bodega_id_6cc5cfd5 ON public.stock_minimo USING btree (bodega_id);


--
-- Name: stock_minimo_producto_id_64aca466; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX stock_minimo_producto_id_64aca466 ON public.stock_minimo USING btree (producto_id);


--
-- Name: token_blacklist_outstandingtoken_jti_hex_d9bdf6f7_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX token_blacklist_outstandingtoken_jti_hex_d9bdf6f7_like ON public.token_blacklist_outstandingtoken USING btree (jti varchar_pattern_ops);


--
-- Name: token_blacklist_outstandingtoken_user_id_83bc629a; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX token_blacklist_outstandingtoken_user_id_83bc629a ON public.token_blacklist_outstandingtoken USING btree (user_id);


--
-- Name: transferencias_bodega_destino_id_c05f57ea; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX transferencias_bodega_destino_id_c05f57ea ON public.transferencias USING btree (bodega_destino_id);


--
-- Name: transferencias_bodega_origen_id_be75c53e; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX transferencias_bodega_origen_id_be75c53e ON public.transferencias USING btree (bodega_origen_id);


--
-- Name: transferencias_usuario_id_eb86f335; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX transferencias_usuario_id_eb86f335 ON public.transferencias USING btree (usuario_id);


--
-- Name: ubicaciones_nivel_id_58da9348; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ubicaciones_nivel_id_58da9348 ON public.ubicaciones USING btree (nivel_id);


--
-- Name: usuarios_email_ef44a1d6_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX usuarios_email_ef44a1d6_like ON public.usuarios USING btree (email varchar_pattern_ops);


--
-- Name: usuarios_groups_group_id_18c61092; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX usuarios_groups_group_id_18c61092 ON public.usuarios_groups USING btree (group_id);


--
-- Name: usuarios_groups_usuario_id_1132ca50; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX usuarios_groups_usuario_id_1132ca50 ON public.usuarios_groups USING btree (usuario_id);


--
-- Name: usuarios_rol_id_fa223853; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX usuarios_rol_id_fa223853 ON public.usuarios USING btree (rol_id);


--
-- Name: usuarios_user_permissions_permission_id_af615ca1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX usuarios_user_permissions_permission_id_af615ca1 ON public.usuarios_user_permissions USING btree (permission_id);


--
-- Name: usuarios_user_permissions_usuario_id_232fd58d; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX usuarios_user_permissions_usuario_id_232fd58d ON public.usuarios_user_permissions USING btree (usuario_id);


--
-- Name: account account_userId_fkey; Type: FK CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.account
    ADD CONSTRAINT "account_userId_fkey" FOREIGN KEY ("userId") REFERENCES neon_auth."user"(id) ON DELETE CASCADE;


--
-- Name: invitation invitation_inviterId_fkey; Type: FK CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.invitation
    ADD CONSTRAINT "invitation_inviterId_fkey" FOREIGN KEY ("inviterId") REFERENCES neon_auth."user"(id) ON DELETE CASCADE;


--
-- Name: invitation invitation_organizationId_fkey; Type: FK CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.invitation
    ADD CONSTRAINT "invitation_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES neon_auth.organization(id) ON DELETE CASCADE;


--
-- Name: member member_organizationId_fkey; Type: FK CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.member
    ADD CONSTRAINT "member_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES neon_auth.organization(id) ON DELETE CASCADE;


--
-- Name: member member_userId_fkey; Type: FK CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.member
    ADD CONSTRAINT "member_userId_fkey" FOREIGN KEY ("userId") REFERENCES neon_auth."user"(id) ON DELETE CASCADE;


--
-- Name: session session_userId_fkey; Type: FK CONSTRAINT; Schema: neon_auth; Owner: -
--

ALTER TABLE ONLY neon_auth.session
    ADD CONSTRAINT "session_userId_fkey" FOREIGN KEY ("userId") REFERENCES neon_auth."user"(id) ON DELETE CASCADE;


--
-- Name: alertas alertas_bodega_id_d74cdf90_fk_bodegas_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_bodega_id_d74cdf90_fk_bodegas_id FOREIGN KEY (bodega_id) REFERENCES public.bodegas(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: alertas alertas_producto_id_61fe568d_fk_productos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_producto_id_61fe568d_fk_productos_id FOREIGN KEY (producto_id) REFERENCES public.productos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: alertas alertas_tipo_id_7fe22092_fk_tipo_alerta_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alertas
    ADD CONSTRAINT alertas_tipo_id_7fe22092_fk_tipo_alerta_id FOREIGN KEY (tipo_id) REFERENCES public.tipo_alerta(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_group_permissions auth_group_permissio_permission_id_84c5c92e_fk_auth_perm; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissio_permission_id_84c5c92e_fk_auth_perm FOREIGN KEY (permission_id) REFERENCES public.auth_permission(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_group_permissions auth_group_permissions_group_id_b120cbf9_fk_auth_group_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissions_group_id_b120cbf9_fk_auth_group_id FOREIGN KEY (group_id) REFERENCES public.auth_group(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_permission auth_permission_content_type_id_2f476e4b_fk_django_co; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_permission
    ADD CONSTRAINT auth_permission_content_type_id_2f476e4b_fk_django_co FOREIGN KEY (content_type_id) REFERENCES public.django_content_type(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: codigos_barra codigos_barra_producto_id_30897e80_fk_productos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.codigos_barra
    ADD CONSTRAINT codigos_barra_producto_id_30897e80_fk_productos_id FOREIGN KEY (producto_id) REFERENCES public.productos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auditoria core_auditoria_usuario_id_124e9f95_fk_usuarios_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auditoria
    ADD CONSTRAINT core_auditoria_usuario_id_124e9f95_fk_usuarios_id FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: detalle_movimiento detalle_movimiento_movimiento_id_0cc24a90_fk_movimientos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detalle_movimiento
    ADD CONSTRAINT detalle_movimiento_movimiento_id_0cc24a90_fk_movimientos_id FOREIGN KEY (movimiento_id) REFERENCES public.movimientos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: detalle_movimiento detalle_movimiento_producto_id_96c53934_fk_productos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detalle_movimiento
    ADD CONSTRAINT detalle_movimiento_producto_id_96c53934_fk_productos_id FOREIGN KEY (producto_id) REFERENCES public.productos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: detalle_transferencia detalle_transferenci_transferencia_id_9067972d_fk_transfere; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detalle_transferencia
    ADD CONSTRAINT detalle_transferenci_transferencia_id_9067972d_fk_transfere FOREIGN KEY (transferencia_id) REFERENCES public.transferencias(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: detalle_transferencia detalle_transferencia_producto_id_dece154d_fk_productos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.detalle_transferencia
    ADD CONSTRAINT detalle_transferencia_producto_id_dece154d_fk_productos_id FOREIGN KEY (producto_id) REFERENCES public.productos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: django_admin_log django_admin_log_content_type_id_c4bce8eb_fk_django_co; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_admin_log
    ADD CONSTRAINT django_admin_log_content_type_id_c4bce8eb_fk_django_co FOREIGN KEY (content_type_id) REFERENCES public.django_content_type(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: django_admin_log django_admin_log_user_id_c564eba6_fk_usuarios_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_admin_log
    ADD CONSTRAINT django_admin_log_user_id_c564eba6_fk_usuarios_id FOREIGN KEY (user_id) REFERENCES public.usuarios(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: envios_alertas_sms envios_alertas_sms_bodega_id_19d5e198_fk_bodegas_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.envios_alertas_sms
    ADD CONSTRAINT envios_alertas_sms_bodega_id_19d5e198_fk_bodegas_id FOREIGN KEY (bodega_id) REFERENCES public.bodegas(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: envios_alertas_sms envios_alertas_sms_producto_id_7a718ae5_fk_productos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.envios_alertas_sms
    ADD CONSTRAINT envios_alertas_sms_producto_id_7a718ae5_fk_productos_id FOREIGN KEY (producto_id) REFERENCES public.productos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: estado_stock_sms estado_stock_sms_bodega_id_59b10898_fk_bodegas_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.estado_stock_sms
    ADD CONSTRAINT estado_stock_sms_bodega_id_59b10898_fk_bodegas_id FOREIGN KEY (bodega_id) REFERENCES public.bodegas(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: estado_stock_sms estado_stock_sms_producto_id_e10f02a6_fk_productos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.estado_stock_sms
    ADD CONSTRAINT estado_stock_sms_producto_id_e10f02a6_fk_productos_id FOREIGN KEY (producto_id) REFERENCES public.productos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: estanterias estanterias_pasillo_id_d20195ea_fk_pasillos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.estanterias
    ADD CONSTRAINT estanterias_pasillo_id_d20195ea_fk_pasillos_id FOREIGN KEY (pasillo_id) REFERENCES public.pasillos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: historial_movimientos historial_movimientos_producto_id_b842760b_fk_productos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.historial_movimientos
    ADD CONSTRAINT historial_movimientos_producto_id_b842760b_fk_productos_id FOREIGN KEY (producto_id) REFERENCES public.productos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: log_alertas log_alertas_alerta_id_ca6f9a28_fk_alertas_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.log_alertas
    ADD CONSTRAINT log_alertas_alerta_id_ca6f9a28_fk_alertas_id FOREIGN KEY (alerta_id) REFERENCES public.alertas(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: log_alertas log_alertas_usuario_id_6a7d481e_fk_usuarios_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.log_alertas
    ADD CONSTRAINT log_alertas_usuario_id_6a7d481e_fk_usuarios_id FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: mermas mermas_bodega_id_e72d471d_fk_bodegas_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mermas
    ADD CONSTRAINT mermas_bodega_id_e72d471d_fk_bodegas_id FOREIGN KEY (bodega_id) REFERENCES public.bodegas(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: mermas mermas_motivo_id_e94f2ce0_fk_motivo_merma_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mermas
    ADD CONSTRAINT mermas_motivo_id_e94f2ce0_fk_motivo_merma_id FOREIGN KEY (motivo_id) REFERENCES public.motivo_merma(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: mermas mermas_producto_id_c32a1cd0_fk_productos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mermas
    ADD CONSTRAINT mermas_producto_id_c32a1cd0_fk_productos_id FOREIGN KEY (producto_id) REFERENCES public.productos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: mermas mermas_usuario_id_4773ed89_fk_usuarios_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mermas
    ADD CONSTRAINT mermas_usuario_id_4773ed89_fk_usuarios_id FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: movimientos movimientos_bodega_id_682f4e93_fk_bodegas_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.movimientos
    ADD CONSTRAINT movimientos_bodega_id_682f4e93_fk_bodegas_id FOREIGN KEY (bodega_id) REFERENCES public.bodegas(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: movimientos movimientos_tipo_id_ace2a658_fk_tipo_movimiento_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.movimientos
    ADD CONSTRAINT movimientos_tipo_id_ace2a658_fk_tipo_movimiento_id FOREIGN KEY (tipo_id) REFERENCES public.tipo_movimiento(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: movimientos movimientos_usuario_id_b1414a4b_fk_usuarios_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.movimientos
    ADD CONSTRAINT movimientos_usuario_id_b1414a4b_fk_usuarios_id FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: niveles niveles_estanteria_id_7afcb597_fk_estanterias_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.niveles
    ADD CONSTRAINT niveles_estanteria_id_7afcb597_fk_estanterias_id FOREIGN KEY (estanteria_id) REFERENCES public.estanterias(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: notificaciones notificaciones_usuario_destino_id_9821f7d5_fk_usuarios_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notificaciones
    ADD CONSTRAINT notificaciones_usuario_destino_id_9821f7d5_fk_usuarios_id FOREIGN KEY (usuario_destino_id) REFERENCES public.usuarios(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: pasillos pasillos_bodega_id_386dc501_fk_bodegas_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pasillos
    ADD CONSTRAINT pasillos_bodega_id_386dc501_fk_bodegas_id FOREIGN KEY (bodega_id) REFERENCES public.bodegas(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: producto_ubicacion producto_ubicacion_producto_id_74d5aaa9_fk_productos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.producto_ubicacion
    ADD CONSTRAINT producto_ubicacion_producto_id_74d5aaa9_fk_productos_id FOREIGN KEY (producto_id) REFERENCES public.productos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: producto_ubicacion producto_ubicacion_ubicacion_id_86be175a_fk_ubicaciones_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.producto_ubicacion
    ADD CONSTRAINT producto_ubicacion_ubicacion_id_86be175a_fk_ubicaciones_id FOREIGN KEY (ubicacion_id) REFERENCES public.ubicaciones(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: productos productos_ficha_externa_id_910e0805_fk_fichas_pr; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.productos
    ADD CONSTRAINT productos_ficha_externa_id_910e0805_fk_fichas_pr FOREIGN KEY (ficha_externa_id) REFERENCES public.fichas_producto_externas(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reportes reportes_tipo_id_6eb23b1c_fk_tipo_reporte_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reportes
    ADD CONSTRAINT reportes_tipo_id_6eb23b1c_fk_tipo_reporte_id FOREIGN KEY (tipo_id) REFERENCES public.tipo_reporte(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reportes reportes_usuario_id_618c502b_fk_usuarios_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reportes
    ADD CONSTRAINT reportes_usuario_id_618c502b_fk_usuarios_id FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: rol_permiso rol_permiso_permiso_id_45298b7d_fk_permisos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rol_permiso
    ADD CONSTRAINT rol_permiso_permiso_id_45298b7d_fk_permisos_id FOREIGN KEY (permiso_id) REFERENCES public.permisos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: rol_permiso rol_permiso_rol_id_b275ea9d_fk_roles_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rol_permiso
    ADD CONSTRAINT rol_permiso_rol_id_b275ea9d_fk_roles_id FOREIGN KEY (rol_id) REFERENCES public.roles(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: sesiones sesiones_usuario_id_caef39af_fk_usuarios_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sesiones
    ADD CONSTRAINT sesiones_usuario_id_caef39af_fk_usuarios_id FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: stock_bodega stock_bodega_bodega_id_be346900_fk_bodegas_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_bodega
    ADD CONSTRAINT stock_bodega_bodega_id_be346900_fk_bodegas_id FOREIGN KEY (bodega_id) REFERENCES public.bodegas(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: stock_bodega stock_bodega_producto_id_5086e50b_fk_productos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_bodega
    ADD CONSTRAINT stock_bodega_producto_id_5086e50b_fk_productos_id FOREIGN KEY (producto_id) REFERENCES public.productos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: stock_minimo stock_minimo_bodega_id_6cc5cfd5_fk_bodegas_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_minimo
    ADD CONSTRAINT stock_minimo_bodega_id_6cc5cfd5_fk_bodegas_id FOREIGN KEY (bodega_id) REFERENCES public.bodegas(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: stock_minimo stock_minimo_producto_id_64aca466_fk_productos_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_minimo
    ADD CONSTRAINT stock_minimo_producto_id_64aca466_fk_productos_id FOREIGN KEY (producto_id) REFERENCES public.productos(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: token_blacklist_blacklistedtoken token_blacklist_blacklistedtoken_token_id_3cc7fe56_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.token_blacklist_blacklistedtoken
    ADD CONSTRAINT token_blacklist_blacklistedtoken_token_id_3cc7fe56_fk FOREIGN KEY (token_id) REFERENCES public.token_blacklist_outstandingtoken(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: token_blacklist_outstandingtoken token_blacklist_outs_user_id_83bc629a_fk_usuarios_; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.token_blacklist_outstandingtoken
    ADD CONSTRAINT token_blacklist_outs_user_id_83bc629a_fk_usuarios_ FOREIGN KEY (user_id) REFERENCES public.usuarios(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: transferencias transferencias_bodega_destino_id_c05f57ea_fk_bodegas_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transferencias
    ADD CONSTRAINT transferencias_bodega_destino_id_c05f57ea_fk_bodegas_id FOREIGN KEY (bodega_destino_id) REFERENCES public.bodegas(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: transferencias transferencias_bodega_origen_id_be75c53e_fk_bodegas_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transferencias
    ADD CONSTRAINT transferencias_bodega_origen_id_be75c53e_fk_bodegas_id FOREIGN KEY (bodega_origen_id) REFERENCES public.bodegas(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: transferencias transferencias_usuario_id_eb86f335_fk_usuarios_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transferencias
    ADD CONSTRAINT transferencias_usuario_id_eb86f335_fk_usuarios_id FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: ubicaciones ubicaciones_nivel_id_58da9348_fk_niveles_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ubicaciones
    ADD CONSTRAINT ubicaciones_nivel_id_58da9348_fk_niveles_id FOREIGN KEY (nivel_id) REFERENCES public.niveles(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: usuarios_groups usuarios_groups_group_id_18c61092_fk_auth_group_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios_groups
    ADD CONSTRAINT usuarios_groups_group_id_18c61092_fk_auth_group_id FOREIGN KEY (group_id) REFERENCES public.auth_group(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: usuarios_groups usuarios_groups_usuario_id_1132ca50_fk_usuarios_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios_groups
    ADD CONSTRAINT usuarios_groups_usuario_id_1132ca50_fk_usuarios_id FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: usuarios usuarios_rol_id_fa223853_fk_roles_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_rol_id_fa223853_fk_roles_id FOREIGN KEY (rol_id) REFERENCES public.roles(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: usuarios_user_permissions usuarios_user_permis_permission_id_af615ca1_fk_auth_perm; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios_user_permissions
    ADD CONSTRAINT usuarios_user_permis_permission_id_af615ca1_fk_auth_perm FOREIGN KEY (permission_id) REFERENCES public.auth_permission(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: usuarios_user_permissions usuarios_user_permissions_usuario_id_232fd58d_fk_usuarios_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usuarios_user_permissions
    ADD CONSTRAINT usuarios_user_permissions_usuario_id_232fd58d_fk_usuarios_id FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id) DEFERRABLE INITIALLY DEFERRED;


--
-- PostgreSQL database dump complete
--

\unrestrict zdvzHWLvNE1bWmKU7qsgVISgq6fGBKupnZLa9fZrAWqiAdUUfZftadbQv1BUjAL


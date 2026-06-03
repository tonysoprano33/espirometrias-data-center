-- Modelo inicial PostgreSQL para la app de agenda + espirometria.
-- Puede adaptarse luego al ORM de Django.

create table app_role (
    id bigserial primary key,
    code varchar(30) not null unique,
    name varchar(80) not null
);

create table app_user (
    id bigserial primary key,
    username varchar(150) not null unique,
    full_name varchar(150) not null,
    password_hash text not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

create table app_user_role (
    user_id bigint not null references app_user(id) on delete cascade,
    role_id bigint not null references app_role(id) on delete cascade,
    primary key (user_id, role_id)
);

create table patient (
    id bigserial primary key,
    full_name varchar(150) not null,
    dni varchar(20) not null,
    birth_date date,
    phone varchar(50),
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (dni)
);

create table referring_physician (
    id bigserial primary key,
    full_name varchar(150) not null unique,
    is_default boolean not null default false,
    active boolean not null default true
);

create table encounter (
    id bigserial primary key,
    patient_id bigint not null references patient(id),
    encounter_date date not null,
    encounter_time time,
    study_type varchar(30) not null check (study_type in ('Ciclometria', 'Espirometria')),
    status varchar(30) not null default 'Pendiente' check (
        status in ('Pendiente', 'Cargada', 'Revisada por medico', 'Informe generado', 'Entregada')
    ),
    coverage_type varchar(20) not null check (coverage_type in ('Mutual', 'Particular')),
    coverage_name varchar(120),
    affiliate_number varchar(80),
    referring_physician_id bigint references referring_physician(id),
    created_by bigint references app_user(id),
    updated_by bigint references app_user(id),
    validated_by bigint references app_user(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    validated_at timestamptz
);

create table vital_signs (
    id bigserial primary key,
    encounter_id bigint not null unique references encounter(id) on delete cascade,
    so2_rest integer,
    fc_rest integer,
    ta_rest varchar(30),
    so2_post integer,
    fc_post integer
);

create table walk_test (
    id bigserial primary key,
    encounter_id bigint not null unique references encounter(id) on delete cascade,
    distance_meters integer check (distance_meters in (100, 200)),
    completed boolean,
    stopped boolean,
    symptoms boolean,
    borg_final integer check (borg_final between 0 and 10)
);

create table spirometry_result (
    id bigserial primary key,
    encounter_id bigint not null unique references encounter(id) on delete cascade,
    respiratory_pattern varchar(20) check (
        respiratory_pattern in ('Normal', 'Obstructivo', 'Restrictivo', 'Mixto')
    ),
    obstruction_grade varchar(30) check (
        obstruction_grade in ('Leve', 'Moderada', 'Moderadamente severa', 'Severa')
    ),
    restriction_grade varchar(30) check (
        restriction_grade in ('Leve', 'Moderada', 'Moderadamente severa', 'Severa')
    ),
    bronchodilator_positive boolean,
    physician_comment text
);

create table attachment (
    id bigserial primary key,
    encounter_id bigint not null references encounter(id) on delete cascade,
    file_kind varchar(30) not null check (
        file_kind in ('pdf_resultado', 'foto_resultado', 'informe_docx', 'informe_pdf', 'otro')
    ),
    original_name varchar(255) not null,
    storage_path text not null,
    mime_type varchar(120),
    uploaded_by bigint references app_user(id),
    uploaded_at timestamptz not null default now()
);

create table generated_report (
    id bigserial primary key,
    encounter_id bigint not null references encounter(id) on delete cascade,
    report_type varchar(30) not null check (
        report_type in ('Espirometria', 'Completo', 'Mutual')
    ),
    attachment_id bigint references attachment(id),
    generated_by bigint references app_user(id),
    generated_at timestamptz not null default now(),
    generator_version varchar(50)
);

create table audit_event (
    id bigserial primary key,
    encounter_id bigint references encounter(id) on delete set null,
    user_id bigint references app_user(id) on delete set null,
    event_type varchar(60) not null,
    event_detail text,
    created_at timestamptz not null default now()
);

create index idx_encounter_date on encounter(encounter_date);
create index idx_encounter_patient on encounter(patient_id);
create index idx_attachment_encounter on attachment(encounter_id);
create index idx_report_encounter on generated_report(encounter_id);

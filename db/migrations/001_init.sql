-- Road-Repair Prioritizer: full schema (Constitution 9.2) + RLS + Realtime (9.3). Contract v1.1.0.
create extension if not exists postgis;
create extension if not exists pgcrypto;

create table wards (
  id text primary key, name text not null,
  center_lat double precision not null, center_lng double precision not null,
  boundary jsonb not null
);

create table pois (
  id uuid primary key default gen_random_uuid(),
  type text not null check (type in ('school','hospital')),
  name text not null, lat double precision not null, lng double precision not null,
  ward_id text references wards(id),
  location geography(Point,4326) generated always as
    (st_setsrid(st_makepoint(lng, lat),4326)::geography) stored
);

create table crews (
  id text primary key, name text not null,
  color_index int not null check (color_index between 0 and 2),
  depot_lat double precision not null, depot_lng double precision not null,
  shift_minutes int not null default 480,
  current_lat double precision not null, current_lng double precision not null,
  minutes_used double precision not null default 0,
  updated_at timestamptz not null default now()
);

create table crew_secrets (
  crew_id text primary key references crews(id) on delete cascade,
  key_hash text not null,
  rotated_at timestamptz not null default now()
);

create table potholes (
  id uuid primary key default gen_random_uuid(),
  lat double precision not null, lng double precision not null,
  ward_id text references wards(id),
  road_class text not null default 'secondary' check (road_class in ('main','secondary','lane')),
  source text not null check (source in ('complaint','sensor','both')),
  severity double precision not null check (severity between 0 and 1),
  severity_bucket text not null check (severity_bucket in ('low','medium','high','critical')),
  severity_reasons text[] not null default '{}',
  exposure double precision not null check (exposure between 0 and 1),
  exposure_reasons text[] not null default '{}',
  complaint_count int not null default 0, sensor_event_count int not null default 0,
  confirmation_count int not null default 1, repair_minutes int not null,
  status text not null default 'open' check (status in ('open','fixed')),
  photo_urls text[] not null default '{}',
  needs_review boolean not null default false,
  first_reported_at timestamptz not null default now(),
  last_reported_at timestamptz not null default now(),
  fixed_at timestamptz, updated_at timestamptz not null default now(),
  is_test boolean not null default false,
  location geography(Point,4326) generated always as
    (st_setsrid(st_makepoint(lng, lat),4326)::geography) stored
);
create index potholes_location_gix on potholes using gist (location);
create index potholes_status_idx on potholes (status);
create index potholes_ward_idx on potholes (ward_id);

create table complaints (
  id uuid primary key default gen_random_uuid(),
  client_request_id uuid not null unique,
  pothole_id uuid not null references potholes(id) on delete cascade,
  text text not null check (char_length(text) between 5 and 1000),
  photo_url text, lat double precision not null, lng double precision not null,
  road_class text check (road_class in ('main','secondary','lane')),
  text_score double precision, photo_score double precision,
  gps_accuracy_m double precision check (gps_accuracy_m is null or gps_accuracy_m between 0 and 5000),
  photo_verification text not null default 'none'
    check (photo_verification in ('none','verified','unverified','mismatch','duplicate')),
  photo_phash bigint,
  created_at timestamptz not null default now(), is_test boolean not null default false
);
create index complaints_pothole_idx on complaints (pothole_id);
create index complaints_phash_idx on complaints (created_at) where photo_phash is not null;

create table sensor_events (
  id uuid primary key default gen_random_uuid(),
  client_event_id uuid not null unique,
  pothole_id uuid not null references potholes(id) on delete cascade,
  device_id uuid not null,
  lat double precision not null, lng double precision not null,
  peak_z_deviation double precision not null check (peak_z_deviation >= 3.0),
  duration_ms int not null check (duration_ms > 0),
  speed_kmh double precision not null check (speed_kmh >= 0),
  recorded_at timestamptz not null, sensor_score double precision not null,
  created_at timestamptz not null default now(), is_test boolean not null default false
);
create index sensor_events_pothole_idx on sensor_events (pothole_id);
create index sensor_events_device_idx on sensor_events (device_id);

-- Row Level Security on every table
alter table wards         enable row level security;
alter table pois          enable row level security;
alter table crews         enable row level security;
alter table crew_secrets  enable row level security;   -- no policies, on purpose
alter table potholes      enable row level security;
alter table complaints    enable row level security;
alter table sensor_events enable row level security;

create policy anon_read_wards    on wards    for select to anon using (true);
create policy anon_read_pois     on pois     for select to anon using (true);
create policy anon_read_crews    on crews    for select to anon using (true);
create policy anon_read_potholes on potholes for select to anon using (true);

-- Realtime: potholes and crews only
alter publication supabase_realtime add table potholes, crews;

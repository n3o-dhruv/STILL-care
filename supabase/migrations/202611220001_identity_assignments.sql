begin;
create table public.profiles (
 user_id uuid primary key references auth.users on delete cascade,
 full_name text not null default '' check(length(full_name)<=160),
 role text not null default 'patient' check(role in ('patient','consultant')),
 avatar_url text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table public.consultants (
 user_id uuid primary key references public.profiles on delete cascade,
 consultant_id text not null unique default ('SC-'||upper(substr(replace(gen_random_uuid()::text,'-',''),1,16))),
 verification_status text not null default 'pending' check(verification_status in ('pending','approved','rejected')),
 professional_description text not null default '' check(length(professional_description)<=4000)
);
create table public.consultant_requests (
 request_id uuid primary key default gen_random_uuid(), patient_id uuid not null references public.profiles,
 consultant_id uuid not null references public.consultants, status text not null default 'pending' check(status in ('pending','accepted','rejected')),
 created_at timestamptz not null default now(), reviewed_at timestamptz,
 unique(patient_id,consultant_id), check(patient_id<>consultant_id)
);
create table public.consultant_assignments (
 patient_id uuid primary key references public.profiles, consultant_id uuid not null references public.consultants,
 approved_at timestamptz not null default now(), check(patient_id<>consultant_id)
);
create index on public.consultant_assignments(consultant_id);
create index on public.consultant_requests(consultant_id,status);
create table public.notifications (
 notification_id uuid primary key default gen_random_uuid(), recipient_id uuid not null references public.profiles,
 notification_type text not null, related_record_id uuid, read_at timestamptz, created_at timestamptz not null default now()
);
create index on public.notifications(recipient_id,created_at desc);
create function public.is_approved_consultant() returns boolean language sql stable security definer set search_path=public as $$
 select exists(select 1 from consultants c join profiles p on p.user_id=c.user_id where c.user_id=auth.uid() and c.verification_status='approved' and p.role='consultant'); $$;
create function public.can_access_patient(patient uuid) returns boolean language sql stable security definer set search_path=public as $$
 select auth.uid()=patient or (public.is_approved_consultant() and exists(select 1 from consultant_assignments where patient_id=patient and consultant_id=auth.uid())); $$;
create function public.new_profile() returns trigger language plpgsql security definer set search_path=public as $$ begin
 insert into profiles(user_id,full_name) values(new.id,left(coalesce(new.raw_user_meta_data->>'full_name',''),160)); return new; end; $$;
create trigger create_profile after insert on auth.users for each row execute function public.new_profile();
insert into profiles(user_id,full_name) select id,left(coalesce(raw_user_meta_data->>'full_name',''),160) from auth.users on conflict do nothing;
create function public.touch_profile() returns trigger language plpgsql as $$ begin new.updated_at=now();return new;end; $$;
create trigger profile_updated before update on profiles for each row execute function public.touch_profile();
alter table profiles enable row level security;
alter table consultants enable row level security;
alter table consultant_requests enable row level security;
alter table consultant_assignments enable row level security;
alter table notifications enable row level security;
create policy profile_read on profiles for select to authenticated using(user_id=auth.uid() or public.can_access_patient(user_id) or exists(select 1 from consultant_assignments a where a.patient_id=auth.uid() and a.consultant_id=profiles.user_id));
create policy profile_update on profiles for update to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid());
create policy consultant_read on consultants for select to authenticated using(user_id=auth.uid() or exists(select 1 from consultant_assignments a where a.patient_id=auth.uid() and a.consultant_id=consultants.user_id));
create policy consultant_edit on consultants for update to authenticated using(user_id=auth.uid() and public.is_approved_consultant()) with check(user_id=auth.uid());
create policy request_read on consultant_requests for select to authenticated using(patient_id=auth.uid() or (consultant_id=auth.uid() and public.is_approved_consultant()));
create policy assignment_read on consultant_assignments for select to authenticated using(patient_id=auth.uid() or (consultant_id=auth.uid() and public.is_approved_consultant()));
create policy notification_read on notifications for select to authenticated using(recipient_id=auth.uid());
create policy notification_update on notifications for update to authenticated using(recipient_id=auth.uid()) with check(recipient_id=auth.uid());
revoke all on profiles,consultants,consultant_requests,consultant_assignments,notifications from anon,authenticated;
grant select on profiles,consultants,consultant_requests,consultant_assignments,notifications to authenticated;
grant update(full_name,avatar_url) on profiles to authenticated;
grant update(professional_description) on consultants to authenticated;
grant update(read_at) on notifications to authenticated;
create function public.request_consultant(code text) returns uuid language plpgsql security definer set search_path=public as $$
declare target uuid; rid uuid; begin
 if auth.uid() is null or not exists(select 1 from auth.users where id=auth.uid() and email_confirmed_at is not null) or not exists(select 1 from profiles where user_id=auth.uid() and role='patient') then raise exception 'Verified patient account required';end if;
 select c.user_id into target from consultants c join profiles p on p.user_id=c.user_id where c.consultant_id=trim(code) and c.verification_status='approved' and p.role='consultant';
 if target is null then raise exception 'Invalid or unapproved Consultant ID';end if;
 if exists(select 1 from consultant_assignments where patient_id=auth.uid()) then raise exception 'Consultant already assigned';end if;
 insert into consultant_requests(patient_id,consultant_id) values(auth.uid(),target) on conflict(patient_id,consultant_id) do nothing returning request_id into rid;
 if rid is not null then insert into notifications(recipient_id,notification_type,related_record_id) values(target,'assignment_request',rid);else select request_id into rid from consultant_requests where patient_id=auth.uid() and consultant_id=target;end if;return rid;
end; $$;
create function public.review_request(request uuid, accept boolean) returns void language plpgsql security definer set search_path=public as $$
declare r consultant_requests;begin
 if not public.is_approved_consultant() then raise exception 'Approved consultant required';end if;
 select * into r from consultant_requests where request_id=request and consultant_id=auth.uid() for update;
 if r.request_id is null or r.status<>'pending' then raise exception 'Pending request not found';end if;
 if accept then insert into consultant_assignments(patient_id,consultant_id) values(r.patient_id,auth.uid());end if;
 update consultant_requests set status=case when accept then 'accepted' else 'rejected' end,reviewed_at=now() where request_id=request;
 insert into notifications(recipient_id,notification_type,related_record_id) values(r.patient_id,case when accept then 'assignment_accepted' else 'assignment_rejected' end,request);
end; $$;
revoke execute on function public.request_consultant(text),public.review_request(uuid,boolean) from public,anon;
grant execute on function public.request_consultant(text),public.review_request(uuid,boolean) to authenticated;
commit;

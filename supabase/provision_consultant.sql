-- Run ONLY in the Supabase SQL editor as project administrator.
-- First create/invite the consultant via Authentication > Users and verify email.
-- Replace the email below with that account's actual email. Never expose this as an RPC.
begin;
do $$
declare target uuid;
begin
 select id into target from auth.users where lower(email)=lower('REPLACE_WITH_CONSULTANT_EMAIL') and email_confirmed_at is not null;
 if target is null then raise exception 'Verified account not found';end if;
 update public.profiles set role='consultant' where user_id=target;
 insert into public.consultants(user_id,verification_status) values(target,'approved')
 on conflict(user_id) do update set verification_status='approved';
end $$;
commit;
select c.consultant_id,p.full_name from public.consultants c join public.profiles p using(user_id);

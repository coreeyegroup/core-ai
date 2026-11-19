ALTER TABLE conversations DROP CONSTRAINT conversations_mode_check;
ALTER TABLE conversations ADD CONSTRAINT conversations_mode_check
 CHECK (mode IN ('general','quick','professional','deep','research','coding'));

DO $$
DECLARE
    camp RECORD;
    acc_id UUID;
    json_val jsonb;
BEGIN
    -- Cast to text first in the WHERE clause to avoid implicit JSON cast errors
    FOR camp IN SELECT id, sender_account_ids_json::text as json_text FROM campaigns 
                WHERE sender_account_ids_json IS NOT NULL 
                  AND sender_account_ids_json::text NOT IN ('', 'null') LOOP
        BEGIN
            json_val := camp.json_text::jsonb;
            
            IF jsonb_typeof(json_val) = 'array' THEN
                FOR acc_id IN SELECT jsonb_array_elements_text(json_val)::UUID LOOP
                    BEGIN
                        INSERT INTO campaign_accounts (campaign_id, account_id)
                        VALUES (camp.id, acc_id)
                        ON CONFLICT DO NOTHING;
                    EXCEPTION WHEN OTHERS THEN
                        -- Ignore invalid UUIDs or FK violations
                        NULL;
                    END;
                END LOOP;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            -- Ignore casting errors if the text is completely invalid JSON
            NULL;
        END;
    END LOOP;
END $$;

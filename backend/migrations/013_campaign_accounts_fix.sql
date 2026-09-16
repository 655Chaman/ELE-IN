DO $$
DECLARE
    camp RECORD;
    acc_id UUID;
    json_val jsonb;
BEGIN
    FOR camp IN SELECT id, sender_account_ids_json FROM campaigns WHERE sender_account_ids_json IS NOT NULL AND sender_account_ids_json != '' AND sender_account_ids_json != 'null' LOOP
        BEGIN
            json_val := camp.sender_account_ids_json::jsonb;
            
            -- Only process if it is actually a JSON array
            IF jsonb_typeof(json_val) = 'array' THEN
                FOR acc_id IN SELECT jsonb_array_elements_text(json_val)::UUID LOOP
                    BEGIN
                        INSERT INTO campaign_accounts (campaign_id, account_id)
                        VALUES (camp.id, acc_id)
                        ON CONFLICT DO NOTHING;
                    EXCEPTION WHEN OTHERS THEN
                        -- Ignore invalid UUIDs or ghost accounts
                        NULL;
                    END;
                END LOOP;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            -- Ignore casting errors if the text is not valid JSON
            NULL;
        END;
    END LOOP;
END $$;

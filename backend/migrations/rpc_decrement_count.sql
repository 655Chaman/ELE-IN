CREATE OR REPLACE FUNCTION decrement_list_row_count(list_uuid UUID)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE lead_lists
  SET row_count = GREATEST(row_count - 1, 0)
  WHERE id = list_uuid AND row_count > 0;
END;
$$;

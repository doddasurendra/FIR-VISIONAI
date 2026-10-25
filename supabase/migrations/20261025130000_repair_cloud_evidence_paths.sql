-- Repair documents.stored_path for files uploaded to Supabase Storage through the FIR intake and
-- replacement flows. Those flows recorded the temporary local cache copy
-- (".../data/evidence/cloud_cache/{hash8}_{filename}") instead of the storage key, and the cache copy
-- is deleted after processing, so the evidence viewer reported the file as missing.
--
-- The storage key is "evidence/{first 8 chars of file_hash}_{original_filename}" (StorageService).
-- The ids below were checked on 2026-10-25 against storage.objects (bucket "evidence"): each has its
-- object at that key. Only rows that still hold a cloud_cache path are changed, so re-running this
-- is a no-op. No files, pages, OCR text, chunks or embeddings are touched.
--
-- Run as the table owner (fir_app_user): backend/scripts/apply_sql_migration.py

UPDATE public.documents d
SET stored_path = 'evidence/' || left(d.file_hash, 8) || '_' || d.original_filename,
    updated_at = now()
WHERE d.id IN (
    'df95dbfd-4cb7-48ca-97d2-2477c588d089', '61a94ad1-3c45-4bbc-a270-78c590503afa',
    '810c79a4-f4e2-4b23-924f-1499aa831982', 'de451285-7b67-49f5-8155-72a72d8b850e',
    '9dbffa43-b92e-43c4-a248-28cce4f0cd70', 'a907d537-b209-454d-a7ea-83f684874e93',
    '14db53f4-53a5-4488-8a52-65f4744e9e4a', '23616dfd-5eee-45b4-8b0b-64f0f032be08',
    '7721f644-e4a0-42bd-ae49-6be91b1b5181', '72971ef7-5b28-4c48-a5d1-739b64fe8f3b',
    '0bb81d44-fa73-4820-900a-aacfa48e79b5', 'dc0e0143-f1e4-4df8-bd68-43d7482dd6c4',
    '0e0f1075-ea57-4d82-9aaf-d71b21c9ad0b', '80b538f7-df68-4de5-a584-8e0fdf510a52',
    '07d711f6-df73-4e97-bf29-cb57835263bc', '0d2f4deb-36eb-400c-bd72-a2fce8f265e9',
    'b85754da-ff2d-41aa-817d-16b6889462fc', 'e76ca779-ad89-4d68-9a32-d6a7ea1e2bec',
    '0155bfc8-5d9e-42ea-8cea-3600b182767c', '10cf7f67-a371-4769-8a38-799996d34e55',
    'e0f5c908-e5aa-4160-ad43-5c876668401e', 'f2daf29c-3ec2-404e-9976-7bb807823993',
    '67b2aeaa-03f1-4fb2-a004-85a61516b0e2', '6468ca26-df3f-4bbc-a2dd-1ef2836a3545',
    'ce0ea054-7314-437c-98b3-43d836d440b5', '69fcf2d9-dfae-404b-9ae2-bac429d79ac3',
    'dbf23eba-4321-4cc4-adfe-349e5b164af0', 'e276151c-d36c-4a4e-b921-a369567dbc74',
    'ac0eb401-b0cc-42cb-a515-f0b08fd8d35d', '763579c9-b7fc-4eed-845f-b532a08702c8',
    'f5d2a06f-2eea-4754-af34-9d513f95147b', 'cef21745-b5ec-42cb-a303-1fd84b190edb',
    '6c277b27-c8e0-4c93-a492-b485cd788356', '2b1542ed-636b-4ca0-8e3d-6a122bbc2473'
)
  AND d.file_hash IS NOT NULL
  AND replace(d.stored_path, '\', '/') LIKE '%/data/evidence/cloud_cache/%';

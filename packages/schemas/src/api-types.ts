// AUTO-GENERATED — do not edit by hand.
// Run `pnpm --filter @chatbot/schemas generate` (with apps/api's dev
// server running) to regenerate from the current OpenAPI schema.

export interface paths {
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health Ready */
        get: operations["health_ready_health_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/register": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Register */
        post: operations["register_auth_register_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Login */
        post: operations["login_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["me_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/organizations/members": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Members */
        get: operations["list_members_organizations_members_get"];
        put?: never;
        /** Create Member */
        post: operations["create_member_organizations_members_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/knowledge-spaces": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Knowledge Spaces */
        get: operations["list_knowledge_spaces_knowledge_spaces_get"];
        put?: never;
        /** Create Knowledge Space */
        post: operations["create_knowledge_space_knowledge_spaces_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/knowledge-spaces/{space_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Knowledge Space */
        get: operations["get_knowledge_space_knowledge_spaces__space_id__get"];
        put?: never;
        post?: never;
        /** Delete Knowledge Space */
        delete: operations["delete_knowledge_space_knowledge_spaces__space_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/knowledge/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Test Knowledge */
        post: operations["test_knowledge_knowledge_test_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Documents */
        get: operations["list_documents_documents_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/documents/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Document */
        get: operations["get_document_documents__document_id__get"];
        put?: never;
        post?: never;
        /** Delete Document */
        delete: operations["delete_document_documents__document_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/documents/{document_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Archive Document
         * @description spec §9: ACTIVE -> ARCHIVED. Correctness needs no Qdrant cleanup — M7's
         *     retrieval already re-verifies status live against Postgres on every
         *     query, so a stale Qdrant point for this version is excluded there
         *     regardless (same reasoning as the worker's auto-supersede logic, M13).
         */
        post: operations["archive_document_documents__document_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/documents/{document_id}/relations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Relations */
        get: operations["list_relations_documents__document_id__relations_get"];
        put?: never;
        /**
         * Create Relation
         * @description spec §21: admin-curated relations between two documents (e.g. "Regulation
         *     B AMENDS Regulation A") — surfaced later as a citation warning by
         *     AdaptiveCitationService so a user citing Regulation A learns it has been
         *     amended, even though Regulation A's own version is still ACTIVE.
         */
        post: operations["create_relation_documents__document_id__relations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/documents/relations/{relation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Relation */
        delete: operations["delete_relation_documents_relations__relation_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/documents/{document_id}/structure": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Document Structure */
        get: operations["get_document_structure_documents__document_id__structure_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/documents/{document_id}/nodes/{node_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Correct Document Node */
        patch: operations["correct_document_node_documents__document_id__nodes__node_id__patch"];
        trace?: never;
    };
    "/documents/{document_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve Document Structure */
        post: operations["approve_document_structure_documents__document_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/documents/upload": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Upload Document */
        post: operations["upload_document_documents_upload_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/documents/{document_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upload New Version
         * @description spec §19: a new DocumentVersion for an EXISTING Document — the
         *     missing link M13's core slice fills in. Once this version's processing
         *     reaches ACTIVE, the worker's index_document task auto-supersedes
         *     whichever version of this document was previously ACTIVE.
         */
        post: operations["upload_new_version_documents__document_id__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/processing-jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Processing Job */
        get: operations["get_processing_job_processing_jobs__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/retrieval/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Search */
        post: operations["search_retrieval_search_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reranking/evidence": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Get Evidence */
        post: operations["get_evidence_reranking_evidence_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/llm/generate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate */
        post: operations["generate_llm_generate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/llm/generate/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Stream */
        post: operations["generate_stream_llm_generate_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/verification/answer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Answer */
        post: operations["answer_verification_answer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Conversations */
        get: operations["list_conversations_conversations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/conversations/{conversation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Conversation */
        get: operations["get_conversation_conversations__conversation_id__get"];
        put?: never;
        post?: never;
        /** Delete Conversation */
        delete: operations["delete_conversation_conversations__conversation_id__delete"];
        options?: never;
        head?: never;
        /** Rename Conversation */
        patch: operations["rename_conversation_conversations__conversation_id__patch"];
        trace?: never;
    };
    "/chat": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Chat */
        post: operations["chat_chat_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/chat/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Chat Stream */
        post: operations["chat_stream_chat_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/analytics/overview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Overview */
        get: operations["get_overview_analytics_overview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/analytics/knowledge-gaps": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Knowledge Gaps */
        get: operations["get_knowledge_gaps_analytics_knowledge_gaps_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/analytics/questions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Top Questions */
        get: operations["get_top_questions_analytics_questions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/analytics/sources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Top Sources */
        get: operations["get_top_sources_analytics_sources_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/messages/{message_id}/feedback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Submit Feedback */
        post: operations["submit_feedback_messages__message_id__feedback_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AnalyticsOverview */
        AnalyticsOverview: {
            /** Total Questions */
            total_questions: number;
            /** Answered */
            answered: number;
            /** Insufficient Evidence */
            insufficient_evidence: number;
            /** Avg Latency Ms */
            avg_latency_ms: number | null;
            /** P95 Latency Ms */
            p95_latency_ms: number | null;
            /** Avg Cost Usd */
            avg_cost_usd: number | null;
            /** Citation Coverage */
            citation_coverage: number;
            /** Retrieval Success */
            retrieval_success: number;
            /** Cache Hit Rate */
            cache_hit_rate: number;
            /** Thumbs Up */
            thumbs_up: number;
            /** Thumbs Down */
            thumbs_down: number;
        };
        /** AnswerRequest */
        AnswerRequest: {
            /** Query */
            query: string;
            /** Knowledge Space Id */
            knowledge_space_id?: string | null;
        };
        /** AnswerResponse */
        AnswerResponse: {
            /** Query */
            query: string;
            /**
             * Tier
             * @enum {string}
             */
            tier: "FAST" | "STRONG";
            /**
             * Retrieval Mode
             * @enum {string}
             */
            retrieval_mode: "EXACT_STRUCTURAL" | "HYBRID";
            /** Reranked */
            reranked: boolean;
            /** Insufficient Evidence */
            insufficient_evidence: boolean;
            /** Reason If Insufficient */
            reason_if_insufficient: string | null;
            answer_type: components["schemas"]["QueryIntent"];
            /** Summary */
            summary: string;
            /** Sections */
            sections: string[];
            /** Claims */
            claims: components["schemas"]["VerifiedClaim"][];
            /** Citations */
            citations: {
                [key: string]: components["schemas"]["Citation"];
            };
        };
        /** ApprovalResult */
        ApprovalResult: {
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /**
             * Document Version Id
             * Format: uuid
             */
            document_version_id: string;
            status: components["schemas"]["DocumentLifecycleStatus"];
        };
        /** ArchiveResult */
        ArchiveResult: {
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /**
             * Document Version Id
             * Format: uuid
             */
            document_version_id: string;
            status: components["schemas"]["DocumentLifecycleStatus"];
        };
        /** Body_upload_document_documents_upload_post */
        Body_upload_document_documents_upload_post: {
            /** File */
            file: string;
            /**
             * Knowledge Space Id
             * Format: uuid
             */
            knowledge_space_id: string;
        };
        /** Body_upload_new_version_documents__document_id__versions_post */
        Body_upload_new_version_documents__document_id__versions_post: {
            /** File */
            file: string;
        };
        /** ChatRequest */
        ChatRequest: {
            /** Query */
            query: string;
            /** Conversation Id */
            conversation_id?: string | null;
            /** Knowledge Space Id */
            knowledge_space_id?: string | null;
        };
        /** ChatResponse */
        ChatResponse: {
            /**
             * Conversation Id
             * Format: uuid
             */
            conversation_id: string;
            /**
             * Message Id
             * Format: uuid
             */
            message_id: string;
            answer: components["schemas"]["AnswerResponse"];
        };
        /** Citation */
        Citation: {
            /** Source Id */
            source_id: string;
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /** Document Title */
            document_title: string;
            /** Structural Path Text */
            structural_path_text: string | null;
            /** Page Start */
            page_start: number;
            /** Page End */
            page_end: number;
            /** Original Text Excerpt */
            original_text_excerpt: string;
            /**
             * Superseding Relations
             * @default []
             */
            superseding_relations: components["schemas"]["RelatingDocument"][];
        };
        /**
         * ClaimStatus
         * @enum {string}
         */
        ClaimStatus: "SUPPORTED" | "UNSUPPORTED" | "UNCERTAIN";
        /** ConversationDetail */
        ConversationDetail: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Messages */
            messages: components["schemas"]["MessagePublic"][];
        };
        /** ConversationPublic */
        ConversationPublic: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** ConversationRenameRequest */
        ConversationRenameRequest: {
            /** Title */
            title: string;
        };
        /** CreateRelationRequest */
        CreateRelationRequest: {
            /**
             * Target Document Id
             * Format: uuid
             */
            target_document_id: string;
            relation_type: components["schemas"]["DocumentRelationType"];
        };
        /**
         * DocumentLifecycleStatus
         * @description Processing/lifecycle status of a DocumentVersion (spec §9).
         *
         *     Distinct from the legal/regulatory validity status (§20, ACTIVE/SUPERSEDED/
         *     REVOKED/DRAFT/ARCHIVED/UNKNOWN) which is not touched until M4+. M2 only ever
         *     sets UPLOADED, PROCESSING, PROCESSING_FAILED — the rest of the enum exists
         *     now so later milestones don't need an enum-alter migration.
         * @enum {string}
         */
        DocumentLifecycleStatus: "UPLOADED" | "PROCESSING" | "PARSED" | "REVIEW_REQUIRED" | "APPROVED" | "INDEXING" | "ACTIVE" | "PROCESSING_FAILED" | "SUPERSEDED" | "ARCHIVED";
        /** DocumentMentionPublic */
        DocumentMentionPublic: {
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /** Document Title */
            document_title: string;
            /** Citation Count */
            citation_count: number;
        };
        /**
         * DocumentNodeType
         * @description Addendum §7 — full vocabulary provisioned now. M3 only ever assigns
         *     the generic types listed in the M3 plan's scope (TITLE/SUBTITLE/SECTION/
         *     SUBSECTION/PARAGRAPH/LIST/LIST_ITEM/TABLE/TABLE_ROW/TABLE_CELL/FIGURE/
         *     APPENDIX/FOOTNOTE/UNKNOWN_BLOCK); specialized types (CHAPTER/ARTICLE/
         *     CLAUSE/LETTER_ITEM/ROMAN_ITEM/NESTED_ITEM/DECISION_ITEM/DIAGRAM/
         *     FLOWCHART/ORGANIZATION_CHART/SIGNATURE_BLOCK/NUMBERED_SECTION/
         *     NUMBERED_ITEM/PART/DOCUMENT/REGION) are reserved for M4.
         * @enum {string}
         */
        DocumentNodeType: "DOCUMENT" | "REGION" | "TITLE" | "SUBTITLE" | "CHAPTER" | "PART" | "SECTION" | "SUBSECTION" | "NUMBERED_SECTION" | "NUMBERED_ITEM" | "LETTER_ITEM" | "ROMAN_ITEM" | "NESTED_ITEM" | "ARTICLE" | "CLAUSE" | "DECISION_ITEM" | "PARAGRAPH" | "LIST" | "LIST_ITEM" | "TABLE" | "TABLE_ROW" | "TABLE_CELL" | "APPENDIX" | "FIGURE" | "DIAGRAM" | "FLOWCHART" | "ORGANIZATION_CHART" | "FOOTNOTE" | "SIGNATURE_BLOCK" | "UNKNOWN_BLOCK";
        /** DocumentPublic */
        DocumentPublic: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
            /**
             * Knowledge Space Id
             * Format: uuid
             */
            knowledge_space_id: string;
            /**
             * Latest Version Id
             * Format: uuid
             */
            latest_version_id: string;
            latest_version_status: components["schemas"]["DocumentLifecycleStatus"];
            /** Latest Processing Job Id */
            latest_processing_job_id: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** DocumentRelationPublic */
        DocumentRelationPublic: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * From Document Id
             * Format: uuid
             */
            from_document_id: string;
            /** From Document Title */
            from_document_title: string;
            /**
             * To Document Id
             * Format: uuid
             */
            to_document_id: string;
            /** To Document Title */
            to_document_title: string;
            relation_type: components["schemas"]["DocumentRelationType"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /**
         * DocumentRelationType
         * @description spec §21 — relational metadata between document versions, stored in
         *     Postgres (never Neo4j/GraphRAG, per §101). M13's core slice only ever
         *     auto-creates SUPERSEDED_BY (see the worker's index_document task); the
         *     rest exist now so a future admin-curated-relations feature needs no
         *     enum-alter migration.
         * @enum {string}
         */
        DocumentRelationType: "AMENDS" | "REPEALS" | "REPLACES" | "IMPLEMENTS" | "REFERS_TO" | "SUPERSEDED_BY";
        /** DocumentStructurePublic */
        DocumentStructurePublic: {
            /**
             * Document Version Id
             * Format: uuid
             */
            document_version_id: string;
            version_status: components["schemas"]["DocumentLifecycleStatus"];
            /** Aggregate Confidence */
            aggregate_confidence: number;
            /** Regions */
            regions: components["schemas"]["StructureRegionPublic"][];
            /** Nodes */
            nodes: components["schemas"]["StructureNodePublic"][];
            profile: components["schemas"]["StructureProfilePublic"] | null;
        };
        /** Evidence */
        Evidence: {
            /** Evidence Id */
            evidence_id: string;
            /**
             * Chunk Id
             * Format: uuid
             */
            chunk_id: string;
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /**
             * Document Version Id
             * Format: uuid
             */
            document_version_id: string;
            /** Structural Path Text */
            structural_path_text: string | null;
            /** Original Text */
            original_text: string;
            /** Page Start */
            page_start: number;
            /** Page End */
            page_end: number;
            /** Parent Context */
            parent_context: string | null;
            /** Relevance Score */
            relevance_score: number | null;
        };
        /** EvidenceRequest */
        EvidenceRequest: {
            /** Query */
            query: string;
            /** Knowledge Space Id */
            knowledge_space_id?: string | null;
        };
        /** EvidenceResponse */
        EvidenceResponse: {
            /** Query */
            query: string;
            /**
             * Retrieval Mode
             * @enum {string}
             */
            retrieval_mode: "EXACT_STRUCTURAL" | "HYBRID";
            /** Reranked */
            reranked: boolean;
            /** Evidence */
            evidence: components["schemas"]["Evidence"][];
        };
        /** FeedbackPublic */
        FeedbackPublic: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Message Id
             * Format: uuid
             */
            message_id: string;
            rating: components["schemas"]["FeedbackRating"];
            /** Comment */
            comment: string | null;
        };
        /**
         * FeedbackRating
         * @enum {string}
         */
        FeedbackRating: "THUMBS_UP" | "THUMBS_DOWN";
        /** FeedbackRequest */
        FeedbackRequest: {
            rating: components["schemas"]["FeedbackRating"];
            /** Comment */
            comment?: string | null;
        };
        /** GenerateRequest */
        GenerateRequest: {
            /** Prompt */
            prompt: string;
            /** Complexity Hint */
            complexity_hint?: ("FAST" | "STRONG") | null;
        };
        /** GenerateResponse */
        GenerateResponse: {
            /** Model Used */
            model_used: string;
            /**
             * Tier
             * @enum {string}
             */
            tier: "FAST" | "STRONG";
            /** Text */
            text: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** KnowledgeGapPublic */
        KnowledgeGapPublic: {
            /** Query */
            query: string;
            /** Frequency */
            frequency: number;
            /**
             * Last Asked At
             * Format: date-time
             */
            last_asked_at: string;
        };
        /** KnowledgeSpaceCreateRequest */
        KnowledgeSpaceCreateRequest: {
            /** Name */
            name: string;
        };
        /** KnowledgeSpacePublic */
        KnowledgeSpacePublic: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** LoginRequest */
        LoginRequest: {
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Password */
            password: string;
        };
        /** MePublic */
        MePublic: {
            user: components["schemas"]["UserPublic"];
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            role: components["schemas"]["OrgRole"];
        };
        /** MemberCreateRequest */
        MemberCreateRequest: {
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Password */
            password: string;
            /** Full Name */
            full_name?: string | null;
            role: components["schemas"]["OrgRole"];
        };
        /** MemberPublic */
        MemberPublic: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Full Name */
            full_name: string | null;
            role: components["schemas"]["OrgRole"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** MessagePublic */
        MessagePublic: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            role: components["schemas"]["MessageRole"];
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /**
         * MessageRole
         * @enum {string}
         */
        MessageRole: "USER" | "ASSISTANT";
        /**
         * NodeCorrectionRequest
         * @description Addendum §27: admin can correct node type/parent/label/title/region
         *     type without ever touching the original extracted text. Any other field
         *     sent in the body (e.g. `text`, `number_raw`) is simply not part of this
         *     schema and is ignored by FastAPI's request binding.
         */
        NodeCorrectionRequest: {
            node_type?: components["schemas"]["DocumentNodeType"] | null;
            /** Parent Id */
            parent_id?: string | null;
            /** Label */
            label?: string | null;
            /** Title */
            title?: string | null;
            region_type?: components["schemas"]["StructuralRegionType"] | null;
        };
        /**
         * OrgRole
         * @enum {string}
         */
        OrgRole: "OWNER" | "ADMIN" | "EDITOR" | "VIEWER";
        /** ProcessingJobPublic */
        ProcessingJobPublic: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            status: components["schemas"]["ProcessingJobStatus"];
            /** Attempts */
            attempts: number;
            /** Error Message */
            error_message: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * ProcessingJobStatus
         * @enum {string}
         */
        ProcessingJobStatus: "QUEUED" | "PROCESSING" | "SUCCEEDED" | "FAILED";
        /**
         * QueryIntent
         * @description spec §30 — minimal vocabulary.
         * @enum {string}
         */
        QueryIntent: "FACTUAL_LOOKUP" | "PROCEDURAL_EXPLANATION" | "LEGAL_BASIS_VALIDATION" | "DEFINITION" | "REQUIREMENT" | "PROHIBITION" | "AUTHORITY" | "DEADLINE" | "COMPARISON" | "DOCUMENT_LOOKUP" | "OTHER";
        /** RegisterRequest */
        RegisterRequest: {
            /** Organization Name */
            organization_name: string;
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Password */
            password: string;
            /** Full Name */
            full_name?: string | null;
        };
        /**
         * RelatingDocument
         * @description spec §21 — a relation where the cited document is the "to" side (e.g.
         *     another regulation AMENDS/REPEALS/REPLACES it), surfaced so a user
         *     citing this document learns it may no longer stand alone even though its
         *     own version is still ACTIVE.
         */
        RelatingDocument: {
            relation_type: components["schemas"]["DocumentRelationType"];
            /**
             * Related Document Id
             * Format: uuid
             */
            related_document_id: string;
            /** Related Document Title */
            related_document_title: string;
        };
        /** RetrievalRequest */
        RetrievalRequest: {
            /** Query */
            query: string;
            /** Knowledge Space Id */
            knowledge_space_id?: string | null;
        };
        /** RetrievalResponse */
        RetrievalResponse: {
            /** Query */
            query: string;
            /**
             * Mode
             * @enum {string}
             */
            mode: "EXACT_STRUCTURAL" | "HYBRID";
            /** Chunks */
            chunks: components["schemas"]["RetrievedChunk"][];
        };
        /** RetrievedChunk */
        RetrievedChunk: {
            /**
             * Chunk Id
             * Format: uuid
             */
            chunk_id: string;
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /**
             * Document Version Id
             * Format: uuid
             */
            document_version_id: string;
            /** Structural Path Text */
            structural_path_text: string | null;
            /** Original Text */
            original_text: string;
            /** Page Start */
            page_start: number;
            /** Page End */
            page_end: number;
            /** Sequence Number */
            sequence_number: number;
            /** Score */
            score: number | null;
            /** Parent Chunk Id */
            parent_chunk_id: string | null;
            /** Token Count */
            token_count: number;
        };
        /** RetrievedSourcePreview */
        RetrievedSourcePreview: {
            /**
             * Chunk Id
             * Format: uuid
             */
            chunk_id: string;
            /** Structural Path Text */
            structural_path_text: string | null;
            /** Original Text */
            original_text: string;
            /** Score */
            score: number | null;
        };
        /**
         * SemanticRole
         * @description Addendum §8 — unused (NULL) until M4's SpecializedStructureInterpreter.
         * @enum {string}
         */
        SemanticRole: "GENERAL" | "PURPOSE" | "OBJECTIVE" | "SCOPE" | "LEGAL_BASIS" | "DEFINITION" | "POSITION" | "PRINCIPLE" | "PLANNING" | "PREPARATION" | "EXECUTION" | "TERMINATION" | "PROCEDURE" | "REQUIREMENT" | "RESPONSIBILITY" | "AUTHORITY" | "DUTY" | "PROHIBITION" | "COMMAND" | "CONTROL" | "DECISION" | "VALIDITY" | "ORGANIZATION_STRUCTURE" | "PROCESS_FLOW" | "CONCLUSION" | "RECOMMENDATION" | "UNKNOWN";
        /**
         * StructuralRegionType
         * @description Addendum §4 — full vocabulary provisioned now. M3 only ever assigns
         *     COVER, TABLE_OF_CONTENTS, APPENDIX, DIAGRAM_REGION, FREEFORM_SECTION, or
         *     UNKNOWN (see M3 plan's region_segmenter heuristics); the rest are reserved
         *     for M4's StructurePatternDetector.
         * @enum {string}
         */
        StructuralRegionType: "COVER" | "TABLE_OF_CONTENTS" | "LEGAL_PREAMBLE" | "LEGAL_BODY" | "LEGAL_DECISION" | "TECHNICAL_GUIDELINE" | "PROCEDURAL_GUIDELINE" | "NUMBERED_MANUAL" | "SOP" | "APPENDIX" | "TABLE_REGION" | "DIAGRAM_REGION" | "ORGANIZATION_CHART" | "FLOWCHART" | "EMBEDDED_TEMPLATE" | "ACADEMIC_TEMPLATE" | "FREEFORM_SECTION" | "UNKNOWN";
        /** StructureNodePublic */
        StructureNodePublic: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Region Id
             * Format: uuid
             */
            region_id: string;
            /** Parent Id */
            parent_id: string | null;
            node_type: components["schemas"]["DocumentNodeType"];
            semantic_role: components["schemas"]["SemanticRole"] | null;
            /** Label */
            label: string | null;
            /** Title */
            title: string | null;
            /** Text */
            text: string | null;
            /** Number Raw */
            number_raw: string | null;
            /** Number Normalized */
            number_normalized: string | null;
            /** Depth */
            depth: number;
            /** Sequence Number */
            sequence_number: number;
            /** Page Start */
            page_start: number;
            /** Page End */
            page_end: number;
            /** Confidence */
            confidence: number;
            /** Structural Path Json */
            structural_path_json: {
                [key: string]: unknown;
            }[];
            /** Structural Path Text */
            structural_path_text: string | null;
            /** Structural Depth */
            structural_depth: number;
            /** Chapter Number */
            chapter_number: string | null;
            /** Article Number */
            article_number: string | null;
            /** Clause Number */
            clause_number: string | null;
            /** Letter Number */
            letter_number: string | null;
            /** Appendix Number */
            appendix_number: string | null;
        };
        /** StructureProfilePublic */
        StructureProfilePublic: {
            /** Contains Articles */
            contains_articles: boolean;
            /** Contains Numbered Sections */
            contains_numbered_sections: boolean;
            /** Contains Chapters */
            contains_chapters: boolean;
            /** Contains Decision Preamble */
            contains_decision_preamble: boolean;
            /** Contains Appendices */
            contains_appendices: boolean;
            /** Contains Tables */
            contains_tables: boolean;
            /** Contains Diagrams */
            contains_diagrams: boolean;
            /** Contains Embedded Document */
            contains_embedded_document: boolean;
        };
        /** StructureRegionPublic */
        StructureRegionPublic: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            region_type: components["schemas"]["StructuralRegionType"];
            /** Page Start */
            page_start: number;
            /** Page End */
            page_end: number;
            /** Sequence Number */
            sequence_number: number;
            /** Confidence */
            confidence: number;
        };
        /** TestKnowledgeRequest */
        TestKnowledgeRequest: {
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /** Query */
            query: string;
        };
        /**
         * TestKnowledgeResponse
         * @description §61's exact admin preview fields: Question / Detected Intent /
         *     Retrieved Sources (with Scores) / Answer / Citation.
         */
        TestKnowledgeResponse: {
            /** Question */
            question: string;
            detected_intent: components["schemas"]["QueryIntent"];
            /**
             * Retrieval Mode
             * @enum {string}
             */
            retrieval_mode: "EXACT_STRUCTURAL" | "HYBRID";
            /** Retrieved Sources */
            retrieved_sources: components["schemas"]["RetrievedSourcePreview"][];
            /** Answer */
            answer: string;
            /** Insufficient Evidence */
            insufficient_evidence: boolean;
            /** Reason If Insufficient */
            reason_if_insufficient: string | null;
            /** Citations */
            citations: {
                [key: string]: components["schemas"]["Citation"];
            };
        };
        /** TopQuestionPublic */
        TopQuestionPublic: {
            /** Query */
            query: string;
            /** Frequency */
            frequency: number;
            /**
             * Last Asked At
             * Format: date-time
             */
            last_asked_at: string;
        };
        /** UploadResponse */
        UploadResponse: {
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /**
             * Document Version Id
             * Format: uuid
             */
            document_version_id: string;
            /**
             * Processing Job Id
             * Format: uuid
             */
            processing_job_id: string;
            status: components["schemas"]["DocumentLifecycleStatus"];
        };
        /** UserPublic */
        UserPublic: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Full Name */
            full_name: string | null;
            /** Is Active */
            is_active: boolean;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
        /** VerifiedClaim */
        VerifiedClaim: {
            /** Text */
            text: string;
            /** Source Ids */
            source_ids: string[];
            status: components["schemas"]["ClaimStatus"];
            /** Invalid Reason */
            invalid_reason: string | null;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    health_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    health_ready_health_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    register_auth_register_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RegisterRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MePublic"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    login_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MePublic"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    logout_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    me_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MePublic"];
                };
            };
        };
    };
    list_members_organizations_members_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemberPublic"][];
                };
            };
        };
    };
    create_member_organizations_members_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MemberCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemberPublic"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_knowledge_spaces_knowledge_spaces_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeSpacePublic"][];
                };
            };
        };
    };
    create_knowledge_space_knowledge_spaces_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["KnowledgeSpaceCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeSpacePublic"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_knowledge_space_knowledge_spaces__space_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                space_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeSpacePublic"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_knowledge_space_knowledge_spaces__space_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                space_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    test_knowledge_knowledge_test_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TestKnowledgeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TestKnowledgeResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_documents_documents_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentPublic"][];
                };
            };
        };
    };
    get_document_documents__document_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentPublic"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_document_documents__document_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    archive_document_documents__document_id__archive_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ArchiveResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_relations_documents__document_id__relations_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentRelationPublic"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_relation_documents__document_id__relations_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateRelationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentRelationPublic"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_relation_documents_relations__relation_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                relation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_document_structure_documents__document_id__structure_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentStructurePublic"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    correct_document_node_documents__document_id__nodes__node_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
                node_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NodeCorrectionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StructureNodePublic"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    approve_document_structure_documents__document_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_document_documents_upload_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_document_documents_upload_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UploadResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_new_version_documents__document_id__versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_new_version_documents__document_id__versions_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UploadResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_processing_job_processing_jobs__job_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProcessingJobPublic"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    search_retrieval_search_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RetrievalRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RetrievalResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_evidence_reranking_evidence_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvidenceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvidenceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_llm_generate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GenerateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_stream_llm_generate_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    answer_verification_answer_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnswerRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnswerResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_conversations_conversations_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationPublic"][];
                };
            };
        };
    };
    get_conversation_conversations__conversation_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_conversation_conversations__conversation_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    rename_conversation_conversations__conversation_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConversationRenameRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationPublic"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    chat_chat_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChatRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChatResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    chat_stream_chat_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChatRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_overview_analytics_overview_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnalyticsOverview"];
                };
            };
        };
    };
    get_knowledge_gaps_analytics_knowledge_gaps_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeGapPublic"][];
                };
            };
        };
    };
    get_top_questions_analytics_questions_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TopQuestionPublic"][];
                };
            };
        };
    };
    get_top_sources_analytics_sources_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentMentionPublic"][];
                };
            };
        };
    };
    submit_feedback_messages__message_id__feedback_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                message_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FeedbackRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeedbackPublic"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}

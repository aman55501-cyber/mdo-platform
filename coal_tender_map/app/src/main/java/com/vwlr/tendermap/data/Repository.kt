package com.vwlr.tendermap.data

import com.vwlr.tendermap.Config
import io.github.jan.supabase.createSupabaseClient
import io.github.jan.supabase.postgrest.Postgrest
import io.github.jan.supabase.postgrest.postgrest
import io.github.jan.supabase.postgrest.query.Order

object Db {
    val client = createSupabaseClient(
        supabaseUrl = Config.SUPABASE_URL,
        supabaseKey = Config.SUPABASE_ANON,
    ) { install(Postgrest) }
}

class Repository {
    private val db = Db.client.postgrest

    suspend fun orgProfile(): OrgProfile =
        db["org_profile"].select().decodeList<OrgProfile>().firstOrNull()
            ?: OrgProfile(name = "VWLR")

    suspend fun tenders(): List<TenderWithLocs> {
        val tenders = db["tenders"].select {
            order("deadline", Order.ASCENDING)
        }.decodeList<Tender>()
        val locs = db["locations"].select().decodeList<TenderLocation>()
        val byTender = locs.groupBy { it.tenderId }
        return tenders.map { TenderWithLocs(it, byTender[it.id] ?: emptyList()) }
    }

    suspend fun setHeart(id: String, hearted: Boolean) {
        db["tenders"].update(mapOf("hearted" to hearted)) { filter { eq("id", id) } }
    }

    suspend fun setStatus(id: String, status: String) {
        db["tenders"].update(mapOf("status" to status)) { filter { eq("id", id) } }
    }
}

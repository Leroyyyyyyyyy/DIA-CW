use std::collections::BTreeMap;
use std::sync::Arc;

use async_trait::async_trait;
use chrono::{DateTime, Datelike, NaiveDate, Utc};
use redis::AsyncCommands;
use tokio::sync::RwLock;
use tokio_postgres::NoTls;

use crate::contracts::HubSlice;
use crate::data_hub::{DataHubError, HistoricalSliceStore, RealtimeSliceStore};

pub struct InMemoryRealtimeSliceStore {
    slices: RwLock<BTreeMap<i64, HubSlice>>,
}

impl InMemoryRealtimeSliceStore {
    pub fn new() -> Self {
        Self {
            slices: RwLock::new(BTreeMap::new()),
        }
    }
}

#[async_trait]
impl RealtimeSliceStore for InMemoryRealtimeSliceStore {
    async fn put_slice(&self, slice: &HubSlice) -> Result<(), DataHubError> {
        self.slices
            .write()
            .await
            .insert(slice.hub_ts.timestamp_millis(), slice.clone());
        Ok(())
    }

    async fn get_slice(&self, hub_ts: DateTime<Utc>) -> Result<Option<HubSlice>, DataHubError> {
        Ok(self
            .slices
            .read()
            .await
            .get(&hub_ts.timestamp_millis())
            .cloned())
    }

    async fn list_slices_range(
        &self,
        from_ts: DateTime<Utc>,
        to_ts: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<HubSlice>, DataHubError> {
        let read = self.slices.read().await;
        let mut out = Vec::new();
        for (_, slice) in read.range(from_ts.timestamp_millis()..=to_ts.timestamp_millis()) {
            out.push(slice.clone());
            if out.len() >= limit {
                break;
            }
        }
        Ok(out)
    }
}

pub struct InMemoryHistoricalSliceStore {
    slices: RwLock<BTreeMap<i64, HubSlice>>,
}

impl InMemoryHistoricalSliceStore {
    pub fn new() -> Self {
        Self {
            slices: RwLock::new(BTreeMap::new()),
        }
    }
}

#[async_trait]
impl HistoricalSliceStore for InMemoryHistoricalSliceStore {
    async fn persist_slice(&self, slice: &HubSlice) -> Result<(), DataHubError> {
        self.slices
            .write()
            .await
            .insert(slice.hub_ts.timestamp_millis(), slice.clone());
        Ok(())
    }

    async fn get_slice(&self, hub_ts: DateTime<Utc>) -> Result<Option<HubSlice>, DataHubError> {
        Ok(self
            .slices
            .read()
            .await
            .get(&hub_ts.timestamp_millis())
            .cloned())
    }

    async fn list_slices_range(
        &self,
        from_ts: DateTime<Utc>,
        to_ts: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<HubSlice>, DataHubError> {
        let read = self.slices.read().await;
        let mut out = Vec::new();
        for (_, slice) in read.range(from_ts.timestamp_millis()..=to_ts.timestamp_millis()) {
            out.push(slice.clone());
            if out.len() >= limit {
                break;
            }
        }
        Ok(out)
    }
}

pub struct RedisRealtimeSliceStore {
    client: redis::Client,
    key_prefix: String,
    ttl_secs: u64,
}

impl RedisRealtimeSliceStore {
    pub fn new(
        redis_url: &str,
        key_prefix: impl Into<String>,
        ttl_secs: u64,
    ) -> Result<Self, DataHubError> {
        let client =
            redis::Client::open(redis_url).map_err(|e| DataHubError::Storage(e.to_string()))?;
        Ok(Self {
            client,
            key_prefix: key_prefix.into(),
            ttl_secs: ttl_secs.max(1),
        })
    }

    fn slice_key(&self, hub_ts_ms: i64) -> String {
        format!("{}:slice:{hub_ts_ms}", self.key_prefix)
    }

    fn index_key(&self) -> String {
        format!("{}:slice:index", self.key_prefix)
    }

    fn latest_key(&self, market_id: &str) -> String {
        format!("{}:latest:{market_id}", self.key_prefix)
    }
}

#[async_trait]
impl RealtimeSliceStore for RedisRealtimeSliceStore {
    async fn put_slice(&self, slice: &HubSlice) -> Result<(), DataHubError> {
        let hub_ts_ms = slice.hub_ts.timestamp_millis();
        let slice_key = self.slice_key(hub_ts_ms);
        let index_key = self.index_key();
        let payload =
            serde_json::to_string(slice).map_err(|e| DataHubError::Storage(e.to_string()))?;
        let ttl_ms = (self.ttl_secs as i64) * 1000;
        let cutoff_ms = hub_ts_ms - ttl_ms;

        let mut conn = self
            .client
            .get_multiplexed_async_connection()
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;

        let mut pipe = redis::pipe();
        pipe.atomic()
            .set_ex(&slice_key, payload, self.ttl_secs)
            .zadd(&index_key, hub_ts_ms, hub_ts_ms)
            .cmd("ZREMRANGEBYSCORE")
            .arg(&index_key)
            .arg("-inf")
            .arg(cutoff_ms)
            .ignore();
        for (market_id, snapshot) in &slice.markets {
            let latest_key = self.latest_key(market_id);
            let latest_payload = serde_json::to_string(snapshot)
                .map_err(|e| DataHubError::Storage(e.to_string()))?;
            pipe.set_ex(latest_key, latest_payload, self.ttl_secs);
        }

        pipe.query_async::<()>(&mut conn)
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;
        Ok(())
    }

    async fn get_slice(&self, hub_ts: DateTime<Utc>) -> Result<Option<HubSlice>, DataHubError> {
        let key = self.slice_key(hub_ts.timestamp_millis());
        let mut conn = self
            .client
            .get_multiplexed_async_connection()
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;
        let raw: Option<String> = conn
            .get(key)
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;
        raw.map(|x| serde_json::from_str::<HubSlice>(&x))
            .transpose()
            .map_err(|e| DataHubError::Storage(e.to_string()))
    }

    async fn list_slices_range(
        &self,
        from_ts: DateTime<Utc>,
        to_ts: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<HubSlice>, DataHubError> {
        let mut conn = self
            .client
            .get_multiplexed_async_connection()
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;
        let index_key = self.index_key();
        let ids: Vec<i64> = redis::cmd("ZRANGEBYSCORE")
            .arg(&index_key)
            .arg(from_ts.timestamp_millis())
            .arg(to_ts.timestamp_millis())
            .arg("LIMIT")
            .arg(0)
            .arg(limit)
            .query_async(&mut conn)
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;

        let mut out = Vec::new();
        for id in ids {
            let key = self.slice_key(id);
            let raw: Option<String> = conn
                .get(key)
                .await
                .map_err(|e| DataHubError::Storage(e.to_string()))?;
            if let Some(raw) = raw {
                let parsed: HubSlice =
                    serde_json::from_str(&raw).map_err(|e| DataHubError::Storage(e.to_string()))?;
                out.push(parsed);
            }
        }
        Ok(out)
    }
}

pub struct PostgresHistoricalSliceStore {
    client: Arc<tokio_postgres::Client>,
}

impl PostgresHistoricalSliceStore {
    pub async fn connect(pg_url: &str) -> Result<Self, DataHubError> {
        let (client, connection) = tokio_postgres::connect(pg_url, NoTls)
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;
        tokio::spawn(async move {
            if let Err(err) = connection.await {
                eprintln!("postgres connection error: {err}");
            }
        });

        let store = Self {
            client: Arc::new(client),
        };
        store.init_schema().await?;
        Ok(store)
    }

    async fn init_schema(&self) -> Result<(), DataHubError> {
        self.client
            .execute(
                "CREATE TABLE IF NOT EXISTS hub_slices (
                    hub_ts timestamptz NOT NULL,
                    ingestion_ts timestamptz NOT NULL,
                    slice_json jsonb NOT NULL,
                    market_count int NOT NULL,
                    stale_count int NOT NULL,
                    PRIMARY KEY (hub_ts)
                ) PARTITION BY RANGE (hub_ts)",
                &[],
            )
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;

        self.client
            .execute(
                "CREATE INDEX IF NOT EXISTS idx_hub_slices_hub_ts_desc ON hub_slices (hub_ts DESC)",
                &[],
            )
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;
        Ok(())
    }

    fn month_bounds(hub_ts: DateTime<Utc>) -> Result<(NaiveDate, NaiveDate), DataHubError> {
        let year = hub_ts.year();
        let month = hub_ts.month();
        let start = NaiveDate::from_ymd_opt(year, month, 1)
            .ok_or_else(|| DataHubError::Storage("invalid month start".to_string()))?;
        let (next_y, next_m) = if month == 12 {
            (year + 1, 1)
        } else {
            (year, month + 1)
        };
        let end = NaiveDate::from_ymd_opt(next_y, next_m, 1)
            .ok_or_else(|| DataHubError::Storage("invalid month end".to_string()))?;
        Ok((start, end))
    }

    async fn ensure_partition(&self, hub_ts: DateTime<Utc>) -> Result<(), DataHubError> {
        let (start, end) = Self::month_bounds(hub_ts)?;
        let part_name = format!("hub_slices_{:04}{:02}", start.year(), start.month());
        let sql = format!(
            "CREATE TABLE IF NOT EXISTS {part_name} PARTITION OF hub_slices FOR VALUES FROM ('{start}') TO ('{end}')"
        );
        self.client
            .execute(sql.as_str(), &[])
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;
        Ok(())
    }
}

#[async_trait]
impl HistoricalSliceStore for PostgresHistoricalSliceStore {
    async fn persist_slice(&self, slice: &HubSlice) -> Result<(), DataHubError> {
        self.ensure_partition(slice.hub_ts).await?;
        let payload =
            serde_json::to_value(slice).map_err(|e| DataHubError::Storage(e.to_string()))?;
        self.client
            .execute(
                "INSERT INTO hub_slices (hub_ts, ingestion_ts, slice_json, market_count, stale_count)
                 VALUES ($1, $2, $3, $4, $5)
                 ON CONFLICT (hub_ts)
                 DO UPDATE SET
                    ingestion_ts = EXCLUDED.ingestion_ts,
                    slice_json = EXCLUDED.slice_json,
                    market_count = EXCLUDED.market_count,
                    stale_count = EXCLUDED.stale_count",
                &[
                    &slice.hub_ts,
                    &slice.ingestion_ts,
                    &payload,
                    &(slice.slice_meta.market_count as i32),
                    &(slice.slice_meta.stale_count as i32),
                ],
            )
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;
        Ok(())
    }

    async fn get_slice(&self, hub_ts: DateTime<Utc>) -> Result<Option<HubSlice>, DataHubError> {
        let row = self
            .client
            .query_opt(
                "SELECT slice_json FROM hub_slices WHERE hub_ts = $1",
                &[&hub_ts],
            )
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;
        match row {
            Some(row) => {
                let payload: serde_json::Value = row.get(0);
                let parsed: HubSlice = serde_json::from_value(payload)
                    .map_err(|e| DataHubError::Storage(e.to_string()))?;
                Ok(Some(parsed))
            }
            None => Ok(None),
        }
    }

    async fn list_slices_range(
        &self,
        from_ts: DateTime<Utc>,
        to_ts: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<HubSlice>, DataHubError> {
        let rows = self
            .client
            .query(
                "SELECT slice_json
                 FROM hub_slices
                 WHERE hub_ts >= $1 AND hub_ts <= $2
                 ORDER BY hub_ts ASC
                 LIMIT $3",
                &[&from_ts, &to_ts, &(limit as i64)],
            )
            .await
            .map_err(|e| DataHubError::Storage(e.to_string()))?;
        let mut out = Vec::new();
        for row in rows {
            let payload: serde_json::Value = row.get(0);
            let parsed: HubSlice = serde_json::from_value(payload)
                .map_err(|e| DataHubError::Storage(e.to_string()))?;
            out.push(parsed);
        }
        Ok(out)
    }
}

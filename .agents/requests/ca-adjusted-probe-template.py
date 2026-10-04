import re, sys, duckdb, pathlib
sql=pathlib.Path(sys.argv[1]).read_text()
def view(n):
    m=re.search(rf"(CREATE OR REPLACE TEMP VIEW {n}\s+AS\s+.*?);",sql,re.S|re.I); return m.group(0).replace("bootcamp_students.evangoh_capstone.","")
c=duckdb.connect()
c.execute("create table bronze_corporate_actions(symbol varchar,ex_date date,split_ratio double,source varchar,fetched_ts timestamp)")
c.execute("create table _deduped_daily(symbol varchar,event_ts timestamp,event_date date,open double,high double,low double,close double,volume bigint,vwap double,trade_count int)")
c.execute("create table _universe(symbol varchar)")
c.execute("insert into _universe values('T'),('R')")
# T: 2 splits: 2:1 on d3, 3:1 on d6. true price 100 flat -> raw: d1,d2 600; d3..d5 300 ; d6.. 100. vol raw 10,10,20,20,20,60..
rows=[("T",f"2022-01-0{i}",p,v) for i,(p,v) in enumerate([(600,10),(600,10),(300,20),(300,20),(300,20),(100,60),(100,60)],1)]
# R: reverse 1:10 (ratio .1) on d4: price 10 -> 100
rows+=[("R",f"2022-01-0{i}",p,v) for i,(p,v) in enumerate([(10,1000),(10,1000),(10,1000),(100,100),(100,100)],1)]
for s,d,p,v in rows:
    c.execute("insert into _deduped_daily values(?,?::date,?::date,?,?,?,?,?,?,1)",[s,d+" 00:00:00",d,p,p,p,p,v,p])
c.execute("insert into bronze_corporate_actions values('T','2022-01-03',2,'massive','2026-01-01'),('T','2022-01-06',3,'massive','2026-01-01'),('R','2022-01-04',0.1,'massive','2026-01-01')")
for n in ["_massive_splits","_split_factors","_adjusted"]: c.execute(view(n))
for r in c.execute("select symbol,event_date,cumulative_split_ratio,adj_close,adj_volume,adjusted_return_1d_unmasked from _adjusted order by 1,2").fetchall(): print([round(x,4) if isinstance(x,float) else str(x) for x in r])

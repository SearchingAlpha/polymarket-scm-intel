import json, os

NB_DIR = os.path.join("C:", os.sep, "Users", "kekoi", "Projects", "operations_research", "polymarket-scm-intel", "notebooks")

ctr = [0]
def nid(p):
    ctr[0] += 1
    return p + str(ctr[0]).zfill(4)
def md(src):
    return {"cell_type":"markdown","metadata":{},"source":src,"id":nid("md")}
def code(src):
    return {"cell_type":"code","execution_count":None,"metadata":{},"outputs":[],"source":src,"id":nid("cd")}
def make_nb(cells):
    return {"nbformat":4,"nbformat_minor":5,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.10.0"}},"cells":cells}
def write_nb(name, nb):
    p = os.path.join(NB_DIR, name)
    with open(p,"w",encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
    print("Written:", p)

# ============================================================
# NB1: 01_market_discovery.ipynb
# ============================================================
def build_nb1():
    C = []
    C.append(md("""# 01 - Market Discovery
Systematically find all Polymarket contracts relevant to supply chain disruption."""))
    C.append(code("""import sys
sys.path.insert(0, '..')
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', 80)"""))
    C.append(md("## Step 1: Initialize the Polymarket client and run market discovery"))
    C.append(code("""from src.polymarket.client import PolymarketClient
from src.polymarket.market_discovery import MarketDiscovery

client = PolymarketClient()
discovery = MarketDiscovery(client)

print('Running market discovery (this may take a few minutes)...')
markets_df = discovery.run()
print(f'
Discovered {len(markets_df)} supply-chain-relevant markets')"""))
    C.append(md("## Step 2: Inspect discovered markets"))
    C.append(code("""print(f'Total markets: {len(markets_df)}')
print(f"Active: {(markets_df['status'] == 'active').sum()}")
print(f"Closed/Resolved: {(markets_df['status'] == 'closed').sum()}")
print(f'
By category:')
print(markets_df['category'].value_counts())"""))
    C.append(code("""display_cols = ['market_id', 'title', 'category', 'status', 'volume', 'created_at', 'end_date']
markets_df[display_cols].head(30)"""))
    C.append(md("## Step 3: Visualize market distribution"))
    C.append(code("""import matplotlib.pyplot as plt
import matplotlib as mpl
mpl.rcParams['figure.facecolor'] = 'white'

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Category distribution
cat_counts = markets_df['category'].fillna('uncategorized').value_counts()
axes[0].barh(cat_counts.index, cat_counts.values, color='#1f6aa5')
axes[0].set_xlabel('Number of Markets')
axes[0].set_title('Markets by Category')
for spine in ['top', 'right']:
    axes[0].spines[spine].set_visible(False)

# Status distribution
status_counts = markets_df['status'].value_counts()
axes[1].pie(status_counts.values, labels=status_counts.index, autopct='%1.0f%%',
            colors=['#1f6aa5', '#e07b39'])
axes[1].set_title('Active vs Closed Markets')

plt.tight_layout()
plt.savefig('../output/figures/market_distribution.png', dpi=150, bbox_inches='tight')
plt.show()"""))
    C.append(code("""top_by_volume = markets_df.nlargest(20, 'volume')[['title', 'category', 'status', 'volume']]
print('Top 20 markets by trading volume:')
top_by_volume"""))
    C.append(md("## Summary
The discovery pipeline found the markets above. Proceed to 02_data_collection.ipynb to fetch price histories."))
    return C

write_nb('01_market_discovery.ipynb', make_nb(build_nb1()))

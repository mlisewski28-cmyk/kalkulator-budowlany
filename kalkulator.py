import json
import re
import os
import cloudscraper
from bs4 import BeautifulSoup
import streamlit as st

# =============================================================================
# WCZYTYWANIE PRODUKTÓW Z PLIKU JSON
# =============================================================================
@st.cache_data(ttl=60)
def load_products_from_json(filename="produkty.json") -> dict:
    """Wczytuje strukturę kategorii i produktów z pliku JSON."""
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Błąd podczas odczytu pliku {filename}: {e}")
    return {}

# =============================================================================
# UNIWERSALNY EKSTRAKTOR DANYCH (JSON-LD, META PIXEL, DATALAYER)
# =============================================================================
def extract_product_data(html_content: str) -> dict | None:
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. STRATEGIA A: JSON-LD (Schema.org)
    for script in soup.find_all('script', type='application/ld+json'):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            items = data if isinstance(data, list) else data.get('@graph', [data])
                
            for item in items:
                if isinstance(item, dict) and item.get('@type') in ['Product', 'IndividualProduct']:
                    name = item.get('name')
                    offers = item.get('offers', {})
                    if isinstance(offers, list) and offers:
                        offers = offers[0]
                    
                    price = offers.get('price') or offers.get('lowPrice')
                    
                    if price and name:
                        return {
                            "name": str(name).strip(),
                            "price": float(str(price).replace(',', '.')),
                            "source": "JSON-LD (Schema.org)"
                        }
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    # 2. STRATEGIA B: Meta Pixel (Facebook)
    pixel_match = re.search(
        r"fbq\s*\(\s*['\"]track['\"]\s*,\s*['\"]ViewContent['\"]\s*,\s*(\{.*?\})\s*[\),]", 
        html_content, 
        re.DOTALL
    )
    if pixel_match:
        pixel_data = pixel_match.group(1)
        price_match = re.search(r'["\']?value["\']?\s*:\s*["\']?([\d\.,]+)["\']?', pixel_data)
        name_match = re.search(r'["\']?content_name["\']?\s*:\s*["\']([^"\']+)["\']', pixel_data)
        
        if price_match:
            price_val = price_match.group(1).replace(',', '.')
            name_val = name_match.group(1) if name_match else "Nieznany produkt"
            try:
                return {
                    "name": name_val.strip(),
                    "price": float(price_val),
                    "source": "Meta Pixel"
                }
            except ValueError:
                pass

    # 3. STRATEGIA C: Google Tag Manager (dataLayer)
    datalayer_matches = re.findall(r'dataLayer\.push\s*\(\s*(\{.*?\})\s*\)', html_content, re.DOTALL)
    for dl_text in datalayer_matches:
        name_match = re.search(r'["\']?(?:item_name|content_name|name)["\']?\s*:\s*["\']([^"\']+)["\']', dl_text)
        price_match = re.search(r'["\']?(?:price|value)["\']?\s*:\s*["\']?([\d\.,]+)["\']?', dl_text)
        
        if price_match and name_match:
            try:
                return {
                    "name": name_match.group(1).strip(),
                    "price": float(price_match.group(1).replace(',', '.')),
                    "source": "Google Tag Manager (dataLayer)"
                }
            except ValueError:
                continue

    return None


def fetch_product_info(url: str) -> tuple[dict | None, str | None]:
    try:
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        response = scraper.get(url, timeout=12)
        
        if response.status_code != 200:
            return None, f"Nie udało się połączyć ze stroną (Kod HTTP: {response.status_code})"
        
        data = extract_product_data(response.text)
        if data:
            return data, None
        return None, "Nie odnaleziono struktury ceny na podanej stronie."
    except Exception as e:
        return None, f"Błąd połączenia: {e}"


# =============================================================================
# INTERFEJS UŻYTKOWNIKA (STREAMLIT)
# =============================================================================
st.set_page_config(page_title="Kalkulator Budowlany", page_icon="🏗️", layout="wide")

st.title("🏗️ Kalkulator Kosztów Budowlanych")
st.write("Wybierz pozycję z bazy lub wklej własny link do produktu. Aplikacja automatycznie odczyta cenę ze źródła strony.")

# Wczytanie produktów z pliku JSON
raw_catalog = load_products_from_json()

# Budowanie pełnego katalogu z opcją własnego linku
PRODUCTS_CATALOG = {
    "📌 Własny link": {
        "Wklej własny adres URL...": ""
    }
}
PRODUCTS_CATALOG.update(raw_catalog)

col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("1. Wybór materiału")
    
    # 1. Wybór kategorii
    categories = list(PRODUCTS_CATALOG.keys())
    selected_category = st.selectbox("Wybierz kategorię:", categories)
    
    # 2. Wybór produktu wewnątrz wybranej kategorii
    available_products = PRODUCTS_CATALOG.get(selected_category, {})
    product_names = list(available_products.keys())
    selected_product = st.selectbox("Wybierz produkt:", product_names) if product_names else None
    
    # 3. Pobranie adresu URL
    if selected_category == "📌 Własny link" or selected_product == "Wklej własny adres URL...":
        product_url = st.text_input("Adres URL strony produktu:", placeholder="https://sklep.pl/produkt-123")
    else:
        product_url = available_products.get(selected_product, "")
        st.text_input("Adres URL strony produktu:", value=product_url, disabled=True)

with col_right:
    st.subheader("2. Parametry kosztowe")
    quantity = st.number_input("Zapotrzebowanie (szt. / opakowania):", min_value=1, value=10, step=1)
    labor_cost = st.number_input("Koszt robocizny (PLN):", min_value=0.0, value=500.0, step=50.0)

st.markdown("---")

if st.button("🚀 Oblicz koszty", type="primary"):
    if not product_url or not product_url.startswith("http"):
        st.warning("Wprowadź prawidłowy adres URL rozpoczynający się od http:// lub https://")
    else:
        with st.spinner("Pobieranie danych ze strony hurtowni..."):
            data, error = fetch_product_info(product_url)
        
        if error:
            st.error(error)
        else:
            unit_price = data["price"]
            product_name = data["name"]
            data_source = data["source"]
            
            material_total = unit_price * quantity
            total_cost = material_total + labor_cost
            
            st.success(f"Rozpoznano produkt: **{product_name}**")
            
            # Wyniki kosztorysu
            res_col1, res_col2, res_col3, res_col4 = st.columns(4)
            res_col1.metric("Cena jednostkowa", f"{unit_price:.2f} PLN")
            res_col2.metric("Koszt materiału", f"{material_total:.2f} PLN")
            res_col3.metric("Koszt robocizny", f"{labor_cost:.2f} PLN")
            res_col4.metric("ŁĄCZNY KOSZT", f"{total_cost:.2f} PLN")
            
            st.caption(f"ℹ️ **Źródło danych:** Odczytano automatycznie ze struktury `{data_source}`.")
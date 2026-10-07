import json
import time
import os
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit, urlunsplit

# =============================================================================
# KONFIGURACJA KATEGORII DO POBRANIA
# Wklejasz link do pierwszej strony kategorii — skrypt sam przejdzie przez page/2/, page/3/ itd.
# =============================================================================
CATEGORIES_TO_SCRAPE = [
    {
        "category": "Farby Ogólnego Stosowania",
        "url": "https://mrowkaonline.com/kategoria-produkty/farby/farby-farby/farby-ogolnego-stosowania/?filter_tax_product_cat=7714"
    }
    # Możesz tu dopisać kolejne kategorie w nowym wierszu:
    # {
    #     "category": "Klej i Zaprawy",
    #     "url": "https://mrowkaonline.com/kategoria-produkty/..."
    # }
]

OUTPUT_FILENAME = "produkty.json"


def build_page_url(base_url: str, page_num: int) -> str:
    """Tworzy adres URL dla konkretnej podstrony (np. /page/2/?filter=...)."""
    if page_num == 1:
        return base_url

    split_url = urlsplit(base_url)
    # Wstawienie '/page/N/' przed parametrami ?filter...
    path = split_url.path.rstrip('/') + f"/page/{page_num}/"
    return urlunsplit((split_url.scheme, split_url.netloc, path, split_url.query, split_url.fragment))


def get_scraper():
    return cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )


def extract_products_from_page(scraper, url: str) -> list[dict]:
    """Pobiera i wyciąga towary z pojedynczej strony."""
    products = []
    try:
        response = scraper.get(url, timeout=15)
        # Jeśli strona zwróci 404 lub inny błąd — oznacza to koniec podstron
        if response.status_code != 200:
            return products

        soup = BeautifulSoup(response.text, 'html.parser')

        # Wyciąganie linków do produktów
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(url, href)

            # Towary w tym sklepie mają w adresie frazę '/produkt/'
            if '/produkt/' in full_url:
                title = a_tag.get_text(strip=True) or a_tag.get('title', '')
                clean_title = ' '.join(title.split())

                # Odrzucamy bardzo krótkie lub puste etykiety (np. przyciski "Zobacz")
                if clean_title and len(clean_title) > 3:
                    if not any(p['url'] == full_url for p in products):
                        products.append({
                            "name": clean_title,
                            "url": full_url
                        })
    except Exception as e:
        print(f"⚠️ Błąd pobierania {url}: {e}")

    return products


def scrape_category_with_pagination(category_name: str, start_url: str, max_pages: int = 50) -> dict:
    """Skanuje kategorię przechodząc strona po stronie."""
    scraper = get_scraper()
    category_products = {}
    page = 1

    print(f"\n🚀 Rozpoczynam pobieranie kategorii: '{category_name}'")

    while page <= max_pages:
        page_url = build_page_url(start_url, page)
        print(f"  📄 Skanowanie strony {page}: {page_url}")

        page_products = extract_products_from_page(scraper, page_url)

        # Brak produktów = osiągnęliśmy koniec podstron
        if not page_products:
            print(f"  🏁 Brak produktów na stronie {page}. Koniec podstron dla tej kategorii.")
            break

        new_count = 0
        for prod in page_products:
            if prod["name"] not in category_products:
                category_products[prod["name"]] = prod["url"]
                new_count += 1

        print(f"     ✅ Pobrano {len(page_products)} produktów na tej stronie ({new_count} nowych).")

        # Jeśli na nowej stronie nie ma żadnych nowych produktów, kończymy pętlę
        if new_count == 0 and page > 1:
            print("  🏁 Brak nowych produktów. Koniec podstron.")
            break

        page += 1
        time.sleep(1.5)  # Pauza 1.5 sekundy, żeby nie przeciążyć serwera sklepu

    return category_products


def run_crawler():
    catalog = {}
    if os.path.exists(OUTPUT_FILENAME):
        try:
            with open(OUTPUT_FILENAME, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
        except Exception:
            catalog = {}

    for item in CATEGORIES_TO_SCRAPE:
        cat_name = item["category"]
        start_url = item["url"]

        products = scrape_category_with_pagination(cat_name, start_url)
        if products:
            catalog[cat_name] = products

    with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=4)

    print(f"\n🎉 Sukces! Zapisano wszystkie dane w pliku '{OUTPUT_FILENAME}'.")


if __name__ == "__main__":
    run_crawler()
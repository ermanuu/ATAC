from .transit import STATIC_URL, download, import_gtfs

if __name__ == "__main__":
    print(f"Download GTFS ufficiale: {STATIC_URL}", flush=True)
    import_gtfs(download(STATIC_URL))
    print("GTFS importato e verificato.")

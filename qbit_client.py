import qbittorrentapi
import time
from config import Config, logger

class QBitClientWrapper:
    def __init__(self):
        self.client = qbittorrentapi.Client(
            host=Config.QBIT_HOST,
            port=Config.QBIT_PORT,
            username=Config.QBIT_USERNAME,
            password=Config.QBIT_PASSWORD,
            REQUESTS_ARGS={'timeout': (10, 30)}  # 10s connect, 30s read timeout
        )
        
    def connect(self):
        """Ensures that the client is logged in to qBittorrent WebUI."""
        if not self.client.is_logged_in:
            try:
                self.client.auth_log_in()
                logger.info("Successfully authenticated with qBittorrent WebUI.")
            except qbittorrentapi.LoginFailed as e:
                logger.error(f"qBittorrent login failed. Check password/credentials. Error: {e}")
                raise
            except Exception as e:
                logger.error(f"Failed to connect to qBittorrent WebUI at {Config.QBIT_HOST}:{Config.QBIT_PORT}. Error: {e}")
                raise

    def get_storage_info(self):
        """Fetches free storage on disk (in bytes) and transfer speeds."""
        self.connect()
        try:
            maindata = self.client.sync_maindata()
            server_state = maindata.get('server_state', {})
            free_bytes = server_state.get('free_space_on_disk', 0)
            dl_speed = server_state.get('dl_info_speed', 0)
            up_speed = server_state.get('up_info_speed', 0)
            
            return {
                'free_bytes': free_bytes,
                'dl_speed': dl_speed,
                'up_speed': up_speed
            }
        except Exception as e:
            logger.error(f"Failed to fetch storage info from qBittorrent: {e}")
            raise

    def get_downloads_progress(self):
        """Retrieves list of active downloading, stalled, or checking torrents."""
        self.connect()
        try:
            torrents = self.client.torrents_info()
            active_torrents = []
            for t in torrents:
                # Include torrents that are not finished (progress < 1.0) 
                # or are explicitly in downloading/checking states
                is_active = t.progress < 1.0 or t.state in (
                    'downloading', 'stalledDL', 'checkingDL', 'metaDL', 'allocating'
                )
                if is_active:
                    active_torrents.append({
                        'hash': t.hash,
                        'name': t.name,
                        'progress': t.progress,
                        'state': t.state,
                        'size': t.size,
                        'dlspeed': t.dlspeed,
                        'eta': t.eta,
                        'num_seeds': t.num_seeds,
                        'num_leechs': t.num_leechs
                    })
            return active_torrents
        except Exception as e:
            logger.error(f"Failed to fetch active torrents: {e}")
            raise

    def add_torrent(self, url: str):
        """Adds a torrent or magnet link to qBittorrent."""
        self.connect()
        try:
            # returns 'Ok.' if successful
            result = self.client.torrents_add(urls=url)
            logger.info(f"Successfully added torrent to qBittorrent. WebAPI returned: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to add torrent: {e}")
            raise

    def pause_torrent(self, torrent_hash: str):
        self.connect()
        try:
            self.client.torrents_pause(torrent_hashes=torrent_hash)
            logger.info(f"Paused torrent {torrent_hash}")
        except Exception as e:
            logger.error(f"Failed to pause torrent {torrent_hash}: {e}")
            raise

    def resume_torrent(self, torrent_hash: str):
        self.connect()
        try:
            self.client.torrents_resume(torrent_hashes=torrent_hash)
            logger.info(f"Resumed torrent {torrent_hash}")
        except Exception as e:
            logger.error(f"Failed to resume torrent {torrent_hash}: {e}")
            raise

    def delete_torrent(self, torrent_hash: str, delete_files: bool = False):
        self.connect()
        try:
            self.client.torrents_delete(delete_files=delete_files, torrent_hashes=torrent_hash)
            logger.info(f"Deleted torrent {torrent_hash} (delete_files={delete_files})")
        except Exception as e:
            logger.error(f"Failed to delete torrent {torrent_hash}: {e}")
            raise

    def search_torrents(self, pattern: str, limit: int = 5, timeout: int = 8):
        """Starts an asynchronous search job, polls for results, and returns the top hits."""
        self.connect()
        search_id = None
        try:
            # Proactively trigger an update for search plugins on start
            try:
                self.client.search_update_plugins()
            except Exception:
                pass

            # Check if there are any search plugins installed/enabled
            plugins = self.client.search_plugins()
            enabled_plugins = [p.name for p in plugins if getattr(p, 'enabled', False) or p.get('enabled', False)]
            if not enabled_plugins:
                logger.warning("No enabled search plugins found in qBittorrent.")
                return []

            logger.info(f"Initiating qBittorrent search for pattern: '{pattern}'")
            search_job = self.client.search_start(pattern=pattern, plugins='all', category='all')
            
            # Handle return types of search_start defensively
            if hasattr(search_job, 'id'):
                search_id = search_job.id
            elif isinstance(search_job, dict) and 'id' in search_job:
                search_id = search_job['id']
            else:
                search_id = search_job

            # Poll search status
            start_time = time.time()
            while time.time() - start_time < timeout:
                time.sleep(1)
                try:
                    statuses = self.client.search_status(search_id=search_id)
                except Exception as e:
                    # Sometimes 404 is returned if job completes instantly and gets cleared
                    logger.debug(f"Search status polling error (possibly finished): {e}")
                    break

                total_hits = 0
                status_str = "Running"
                
                if isinstance(statuses, list):
                    job_status = next((job for job in statuses if str(getattr(job, 'id', '')) == str(search_id) or str(job.get('id', '')) == str(search_id)), None)
                    if job_status:
                        total_hits = job_status.get('total', 0) if isinstance(job_status, dict) else getattr(job_status, 'total', 0)
                        status_str = job_status.get('status', 'Running') if isinstance(job_status, dict) else getattr(job_status, 'status', 'Running')
                elif isinstance(statuses, dict):
                    # If single job status is returned
                    total_hits = statuses.get('total', 0)
                    status_str = statuses.get('status', 'Running')

                logger.debug(f"Polling search job {search_id}: status={status_str}, total_hits={total_hits}")
                if status_str == 'Stopped' or total_hits >= 50:
                    break

            # Fetch results
            results_data = self.client.search_results(search_id=search_id, limit=100)
            results = results_data.get('results', []) if isinstance(results_data, dict) else getattr(results_data, 'results', [])
            
            # Sort results by seeders descending
            sorted_results = sorted(results, key=lambda x: int(x.get('nbSeeders', 0) or 0), reverse=True)
            
            return sorted_results[:limit]
            
        except Exception as e:
            logger.error(f"Error during search execution: {e}")
            return []
        finally:
            # Clean up the search job to release slots (maximum 5 concurrent)
            if search_id is not None:
                try:
                    self.client.search_delete(search_id=search_id)
                    logger.debug(f"Deleted search job {search_id}")
                except Exception as e:
                    logger.debug(f"Failed to delete search job {search_id}: {e}")

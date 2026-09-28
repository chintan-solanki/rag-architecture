from pathlib import Path
import yaml

#loads config object from the given configuration path
def load_config(config_path_rel_to_root: str | Path | None):

    if config_path_rel_to_root is None:
        raise ValueError('configuration path must be provided')

    ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent

    path = ROOT_DIR / config_path_rel_to_root

    config = {}
    with path.open() as f:
        config = yaml.safe_load(f)

    #add absolute staging incoming and fetched directory paths (which are relative to the root of the project)
    config['staging']['incoming_dir_path'] = str(ROOT_DIR / 'staging/incoming')
    config['staging']['fetched_dir_path'] = str(ROOT_DIR / 'staging/fetched')

    print(f'incoming dir path: {config['staging']['incoming_dir_path']}')
    print(f'fetched dir path: {config['staging']['fetched_dir_path']}')
    return config

    
import argparse
from pathlib import Path

import polars as pl

LABELS = ('bad', 'good', 'neutral')
REQUIRED_COLUMNS = {'user_review', 'review_type'}


def clean_reviews(df: pl.DataFrame) -> pl.DataFrame:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f'Missing required columns: {sorted(missing)}')

    invalid_labels = set(df['review_type'].drop_nulls().unique()) - set(LABELS)
    if invalid_labels:
        raise ValueError(f'Unexpected review labels: {sorted(invalid_labels)}')

    df = df.filter(
        pl.col('user_review').is_not_null()
        & pl.col('review_type').is_not_null()
        & (pl.col('user_review').str.strip_chars() != '')
    ).unique(keep='first', maintain_order=True)

    if 'film_name' in df.columns and df['film_name'].n_unique() == 1 and df['film_name'][0] == 'Unknown':
        df = df.drop('film_name')

    return df


def print_summary(df: pl.DataFrame):
    print(f'Rows: {df.height}')
    print(f'Columns: {df.columns}')
    print(df['review_type'].value_counts().sort('review_type'))

    conflicting_texts = (
        df.group_by('user_review')
        .agg(pl.col('review_type').n_unique().alias('label_count'))
        .filter(pl.col('label_count') > 1)
        .height
    )
    print(f'Texts with conflicting labels: {conflicting_texts}')


def main():
    parser = argparse.ArgumentParser(description='Validate and deduplicate Kinopoisk reviews.')
    parser.add_argument('input', nargs='?', default='data/data.csv', help='Path to the raw CSV file.')
    parser.add_argument(
        'output',
        nargs='?',
        default='data/kinopoisk_reviews_clean.csv',
        help='Path for the cleaned CSV file.',
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    if input_path.resolve() == output_path.resolve():
        parser.error('Input and output paths must be different.')

    raw_df = pl.read_csv(input_path)
    clean_df = clean_reviews(raw_df)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    clean_df.write_csv(output_path)
    print_summary(clean_df)
    print(f'Saved to {output_path}')


if __name__ == '__main__':
    main()
